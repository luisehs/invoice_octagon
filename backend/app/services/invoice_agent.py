# app/services/invoice_agent.py
"""Modo AI del bot (/onAI) — agente conversacional con Claude API.

SOLO se ejecuta cuando la sesión tiene `ai_until` vigente (lo decide
bot_flow.py). Extrae los datos de texto libre, pregunta lo que falte, confirma
si está pago, muestra resumen y, tras confirmación, llama la herramienta
`crear_invoice`. La creación real usa el MISMO `bot_invoice.create_and_send`
del flujo estático, así el invoice resultante es idéntico.

Tras crear un invoice el modo AI vuelve a OFF automáticamente.
"""
from app.services import bot_invoice, bot_session, telegram_client
from app.services.claude_client import call_claude

SYSTEM_PROMPT = (
    "Eres el asistente de facturación de Octagon (tasaciones de Raimundo Marrero). "
    "El usuario te envía por Telegram los datos de un cliente para crear un invoice. "
    "Tu trabajo:\n\n"
    "1. Extrae del mensaje: nombre del cliente, dirección de la propiedad y monto "
    "(tarifa en USD); y, si los menciona, el número de catastro y el email. Los "
    "mensajes pueden venir en cualquier formato.\n"
    "2. Campos obligatorios: nombre del cliente, dirección y monto. Si falta alguno, "
    "pídelo en UNA sola pregunta breve (agrupa todo lo que falte). No inventes valores. "
    "El catastro y el email son OPCIONALES: inclúyelos solo si los dan, no los exijas.\n"
    "3. Si dan un catastro, la descripción del servicio será "
    "\"Appraisal Report - Catastro <catastro>\"; si no, \"Appraisal Report\".\n"
    "4. Antes de crear SIEMPRE pregunta si el monto ya está pago (sí/no).\n"
    "5. Cuando tengas lo obligatorio y sepas si está pago, muestra un resumen "
    "(cliente, catastro si hay, dirección, email si hay, servicio, monto, y si está "
    "PAGADO o PENDIENTE) y pide confirmación (\"¿Lo registro?\").\n"
    "6. Solo tras la confirmación del usuario llama la herramienta crear_invoice.\n"
    "7. Responde siempre en español, tono breve y profesional. No des explicaciones "
    "técnicas ni menciones que eres una IA."
)

CREAR_INVOICE_TOOL = {
    "name": "crear_invoice",
    "description": (
        "Crea el invoice cuando TODOS los datos obligatorios estén completos y el "
        "usuario haya confirmado."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nombre completo del cliente"},
            "address": {"type": "string", "description": "Dirección de la propiedad tasada"},
            "amount": {"type": "number", "description": "Monto / tarifa en USD"},
            "catastro": {"type": "string", "description": "Número de catastro, opcional"},
            "email": {"type": "string", "description": "Email del cliente, opcional"},
            "is_pay": {"type": "boolean", "description": "true si ya está pago; false si pendiente"},
        },
        "required": ["name", "address", "amount", "is_pay"],
    },
}


async def handle_incoming_message(chat_id: int, text: str, u_id: str, session: dict) -> None:
    """Un turno en modo AI. `session` viene cargada por bot_flow y se guarda aquí."""
    await telegram_client.send_chat_action(chat_id, "typing")

    history = list(session.get("messages") or [])
    history.append({"role": "user", "content": text})

    try:
        response = await call_claude(SYSTEM_PROMPT, history, tools=[CREAR_INVOICE_TOOL])
    except Exception as exc:
        print(f"[agent] error llamando a Claude: {exc}")
        await telegram_client.send_message(
            chat_id, "⚠️ Hubo un error procesando tu mensaje. Intenta de nuevo o usa /offAI."
        )
        return

    content = response.get("content", []) or []
    tool_use = next(
        (b for b in content if b.get("type") == "tool_use" and b.get("name") == "crear_invoice"),
        None,
    )

    if tool_use is not None:
        data = dict(tool_use.get("input", {}) or {})
        created = await bot_invoice.create_and_send(chat_id, u_id, data)
        if created:
            # Invoice creado → modo AI vuelve a OFF y flujo limpio.
            bot_session.ai_turn_off(session)
            bot_session.reset_flow(session)
            bot_session.save_session(chat_id, session)
        return

    text_out = "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
    if not text_out:
        text_out = "🤔 No entendí. ¿Me repites los datos del cliente?"

    history.append({"role": "assistant", "content": text_out})
    session["messages"] = history
    bot_session.save_session(chat_id, session)
    await telegram_client.send_message(chat_id, text_out)
