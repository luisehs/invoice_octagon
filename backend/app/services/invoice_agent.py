# app/services/invoice_agent.py
"""Agente conversacional del bot (Fase C).

Un turno = un mensaje de usuario ya whitelisted (bot_polling hace la whitelist y
los comandos). Aquí: cargar historial de `chat_sessions`, llamar a Claude con el
system prompt (§3.4) y la herramienta `crear_invoice` (§3.3), y responder.

⚠️ FASE C: la herramienta NO crea nada. Cuando el modelo la invoca, respondemos
al chat con "SIMULACIÓN — crearía este invoice:" + el JSON de los datos extraídos
y reseteamos la sesión. La creación real (create_invoice_for_user +
generate_invoice_pdf) llega en la Fase D.
"""
from datetime import date

from app.db.supabase_client import supabase
from app.schemas.invoices import InvoiceCreate
from app.services import telegram_client
from app.services.claude_client import call_claude
from app.services.invoice_service import (
    create_invoice_for_user,
    generate_invoice_pdf,
    get_next_serie_for_user,
)

# --- Constantes del emisor (idénticas a InvoiceModal.tsx::handleSubmit) -----
# El bot debe mandar los MISMOS literales que el frontend para que el PDF del
# chat sea idéntico al del dashboard. i_email e i_address NO se imprimen (el
# template usa texto propio), pero se guardan igual que en el frontend.
ISSUER_NAME = "Raimundo Marrero - TASADOR"
ISSUER_INSCRIPTION = "EPA 780 -CGA 195"
ISSUER_EMAIL = "raimundo.marrero2@gmail.com"
ISSUER_ADDRESS = "Cond. El Centro | 500 Muñoz Rivera Ste 301 San Juan, PR 00918"
BASE_DESCRIPTION = "Appraisal Report"

# --- System prompt (PLAN §3.4) ---------------------------------------------
SYSTEM_PROMPT = (
    "Eres el asistente de facturación de Octagon (tasaciones de Raimundo Marrero). "
    "El usuario te envía por Telegram los datos de un cliente para crear un invoice. "
    "Tu trabajo:\n\n"
    "1. Extrae del mensaje: nombre del cliente, dirección de la propiedad y rate "
    "(tarifa en USD); y, si los menciona, el número de catastro y la fecha. Los "
    "mensajes suelen venir como lista numerada pero pueden venir en cualquier "
    "formato.\n"
    "2. Campos obligatorios: nombre del cliente, dirección de la propiedad y rate. "
    "Si falta alguno, pídelo en UNA sola pregunta breve y clara (agrupa todo lo que "
    "falte en un mismo mensaje). No inventes valores. El email del cliente es "
    "OPCIONAL: inclúyelo solo si lo dan, no lo pidas ni lo exijas.\n"
    "3. La fecha es HOY por defecto; solo usa otra fecha si el usuario la indica "
    "explícitamente (formato YYYY-MM-DD).\n"
    "4. El catastro es opcional; si lo dan, se agrega a la descripción del servicio "
    "(\"Appraisal Report - Catastro ...\"). No lo pidas si no lo mencionan.\n"
    "5. Antes de crear SIEMPRE pregunta si ya se pagó el rate (para marcar el invoice "
    "como pagado o pendiente).\n"
    "6. Cuando tengas lo obligatorio y sepas si está pagado, muestra un resumen "
    "(cliente, dirección, catastro si hay, qty × rate = total, y si está PAGADO o "
    "PENDIENTE) y pide confirmación (\"¿Lo creo?\").\n"
    "7. Solo tras la confirmación del usuario llama la herramienta crear_invoice.\n"
    "8. Responde siempre en español, tono breve y profesional. No des explicaciones "
    "técnicas ni menciones que eres una IA."
)

# --- Herramienta crear_invoice (PLAN §3.3) ---------------------------------
CREAR_INVOICE_TOOL = {
    "name": "crear_invoice",
    "description": (
        "Crea el invoice cuando TODOS los datos obligatorios estén completos y el "
        "usuario haya confirmado."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "billto": {
                "type": "string",
                "description": "Nombre completo del cliente (ej. Francisco J Olivencia Torres)",
            },
            "address": {
                "type": "string",
                "description": "Dirección de la propiedad tasada (se imprime en 'Located at:')",
            },
            "rate": {"type": "number", "description": "Tarifa en USD"},
            "catastro": {
                "type": "string",
                "description": (
                    "Número de catastro, opcional (ej. 023-035-213-08). Si se da, se "
                    "agrega a la descripción del servicio."
                ),
            },
            "qty": {"type": "number", "description": "Cantidad; por defecto 1"},
            "date": {
                "type": "string",
                "description": (
                    "Fecha del invoice en formato YYYY-MM-DD. Omitir si el usuario no "
                    "la menciona (se usa la fecha de hoy)."
                ),
            },
            "email": {
                "type": "string",
                "description": "Email del cliente, OPCIONAL. Inclúyelo solo si lo mencionan.",
            },
            "is_pay": {
                "type": "boolean",
                "description": (
                    "true si el cliente YA pagó el rate; false si está pendiente. "
                    "Pregúntalo antes de crear."
                ),
            },
            "sale_tax": {"type": "number", "description": "Impuesto, si aplica"},
        },
        "required": ["billto", "address", "rate"],
    },
}


# --- Estado de conversación (chat_sessions vía RPC) -------------------------
def load_history(chat_id: int) -> list:
    """Devuelve el historial [{role, content}] de la sesión, o [] si no existe."""
    try:
        resp = supabase.rpc("fn_chat_session_get", {"p_chat_id": chat_id}).execute()
    except Exception as exc:
        print(f"[agent] error en fn_chat_session_get: {exc}")
        return []

    data = resp.data
    if isinstance(data, list):
        data = data[0] if data else None
    if not data or data.get("cs_chat_id") is None:
        return []
    return data.get("cs_messages") or []


def save_history(chat_id: int, messages: list, status: str = "collecting") -> None:
    try:
        supabase.rpc(
            "fn_chat_session_upsert",
            {"p_chat_id": chat_id, "p_messages": messages, "p_status": status},
        ).execute()
    except Exception as exc:
        print(f"[agent] error en fn_chat_session_upsert: {exc}")


def reset_session(chat_id: int) -> None:
    save_history(chat_id, [], "idle")


# --- Mapeo chat -> invoice (alineado con InvoiceModal.tsx) ------------------
def build_invoice_fields(data: dict, today: str) -> dict:
    """Convierte lo extraído por `crear_invoice` en los campos de un invoice,
    aplicando las reglas del frontend:

    - nombre del cliente -> i_billto
    - dirección de la propiedad -> id_adress (lo que se imprime en 'Located at:')
    - rate -> id_rate ; qty por defecto 1
    - fecha -> i_date (hoy si no se dio)
    - catastro (si hay) -> se agrega a la descripción: "Appraisal Report - Catastro ..."
    - emisor (i_name/i_inscription/i_email/i_address) hardcodeado igual que el frontend

    Esta función es pura; la Fase D la reutiliza para crear el invoice real
    (agregando i_serie generada).
    """
    qty = data.get("qty") or 1
    rate = data.get("rate") or 0
    sale_tax = data.get("sale_tax") or 0

    catastro = (data.get("catastro") or "").strip()
    description = BASE_DESCRIPTION
    if catastro:
        description = f"{BASE_DESCRIPTION} - Catastro {catastro}"

    i_date = (data.get("date") or "").strip() or today
    total = qty * rate + sale_tax

    # Email del cliente si lo dieron (opcional); si no, el del emisor. No se imprime.
    client_email = (data.get("email") or "").strip() or ISSUER_EMAIL

    # ¿Se pagó el rate? (sello "PAID" en el PDF). Se pregunta antes de crear.
    is_pay = bool(data.get("is_pay", False))

    return {
        # Emisor (hardcodeado, idéntico a InvoiceModal.tsx); i_email = email del
        # cliente si lo dio, si no el del emisor (ninguno se imprime en el PDF).
        "i_name": ISSUER_NAME,
        "i_inscription": ISSUER_INSCRIPTION,
        "i_email": client_email,
        "i_address": ISSUER_ADDRESS,
        # Variables del chat
        "i_billto": data.get("billto") or "",
        "i_date": i_date,
        "i_total": total,
        "i_is_pay": is_pay,
        "details": [
            {
                "id_number": 1,
                "id_description": description,
                "id_qty": qty,
                "id_rate": rate,
                "id_sale_tax": sale_tax,
                "id_adress": data.get("address") or "",
                "id_adress2": "",
            }
        ],
    }


# --- Turno del agente -------------------------------------------------------
async def handle_incoming_message(chat_id: int, text: str, u_id: str) -> None:
    """Procesa un mensaje conversacional (el chat ya está whitelisted).

    `u_id` es el usuario de la app dueño del invoice (viene de telegram_users).
    """
    await telegram_client.send_chat_action(chat_id, "typing")

    history = load_history(chat_id)
    history.append({"role": "user", "content": text})

    try:
        response = await call_claude(
            SYSTEM_PROMPT, history, tools=[CREAR_INVOICE_TOOL]
        )
    except Exception as exc:
        print(f"[agent] error llamando a Claude: {exc}")
        await telegram_client.send_message(
            chat_id, "⚠️ Hubo un error procesando tu mensaje. Intenta de nuevo."
        )
        return

    content = response.get("content", []) or []

    # ¿El modelo quiere crear el invoice?
    tool_use = next(
        (
            b
            for b in content
            if b.get("type") == "tool_use" and b.get("name") == "crear_invoice"
        ),
        None,
    )
    if tool_use is not None:
        # FASE D: creación real del invoice + PDF.
        tool_input = tool_use.get("input", {})
        try:
            serie = get_next_serie_for_user(u_id, date.today())
            fields = build_invoice_fields(tool_input, date.today().isoformat())
            fields["i_serie"] = serie
            invoice = InvoiceCreate(**fields)
            # i_total ya viene calculado en Python (qty × rate + sale_tax).
            created = create_invoice_for_user(u_id, invoice)  # dict con i_id
            pdf_bytes, _row = generate_invoice_pdf(created["i_id"])
        except Exception as exc:
            # Supabase / PDF / validación falló: avisar y NO corromper la sesión
            # (el historial en BD sigue igual → el usuario puede reintentar).
            print(f"[agent] error creando invoice: {exc}")
            await telegram_client.send_message(
                chat_id, f"⚠️ Hubo un error creando el invoice: {exc}"
            )
            return

        total = fields["i_total"]
        caption = f"✅ Invoice {serie} creado — Total ${total:,.2f}"
        try:
            await telegram_client.send_document(
                chat_id, pdf_bytes, f"invoice_{serie}.pdf", caption=caption
            )
        except Exception as exc:
            # El invoice YA se creó; solo falló el envío del archivo.
            print(f"[agent] invoice {serie} creado pero falló enviar el PDF: {exc}")
            await telegram_client.send_message(
                chat_id,
                f"✅ Invoice {serie} creado (Total ${total:,.2f}), pero no pude "
                "enviar el PDF. Está disponible en el dashboard.",
            )

        # Flujo completo: sesión a idle.
        reset_session(chat_id)
        return

    # Respuesta de texto (falta info / resumen / pide confirmación)
    text_out = "\n".join(
        b.get("text", "") for b in content if b.get("type") == "text"
    ).strip()
    if not text_out:
        text_out = "🤔 No entendí. ¿Me repites los datos del cliente?"

    history.append({"role": "assistant", "content": text_out})
    save_history(chat_id, history)
    await telegram_client.send_message(chat_id, text_out)
