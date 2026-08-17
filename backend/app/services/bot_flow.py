# app/services/bot_flow.py
"""Flujo ESTÁTICO del bot (máquina de estados, sin LLM).

Entrada: un mensaje de texto de un chat ya whitelisted (bot_polling hace la
whitelist y /id, /register). Aquí viven los comandos del flujo, el modo AI
(/onAI, /offAI, con expiración automática) y los estados:

    idle / collecting  --datos completos-->  awaiting_payment
    awaiting_payment   --sí/no-->            awaiting_confirm (muestra resumen)
    awaiting_confirm   --sí-->               crea invoice + PDF → idle
                       --no-->               idle
                       --líneas numeradas--> corrección → re-valida

Todo el texto de respuesta es fijo, en español, generado por código.
"""
from app.core.config import settings
from app.services import bot_invoice, bot_session, telegram_client
from app.services.bot_parser import (
    FIELD_LABELS,
    build_description,
    has_numbered_lines,
    merge_data,
    parse_message,
    parse_yes_no,
    validate,
)
from app.services.bot_session import (
    STATE_AWAITING_CONFIRM,
    STATE_AWAITING_PAYMENT,
    STATE_COLLECTING,
    STATE_IDLE,
)

FORMAT_HELP = (
    "📝 Envíame los datos del cliente en este formato (una línea por punto):\n\n"
    "1. nombre\n"
    "2. catastro\n"
    "3. address\n"
    "4. email\n"
    "5. monto\n\n"
    "Obligatorios: 1 (nombre), 3 (address) y 5 (monto). "
    "El catastro y el email son opcionales.\n"
    "Puedes mandar solo las líneas que falten o corregir una repitiendo su número."
)

WELCOME = (
    "👋 Bot de facturación de Octagon.\n\n" + FORMAT_HELP + "\n\n"
    "Comandos:\n"
    "  /cancelar — reinicia la conversación\n"
    "  /onAI — modo AI (texto libre) por un rato\n"
    "  /offAI — apaga el modo AI\n"
    "  /id — muestra tu chat_id"
)


# --- Helpers de texto -------------------------------------------------------
def _fmt_money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def build_missing_message(missing: list[str], errors: list[str]) -> str:
    parts: list[str] = []
    if missing:
        if len(missing) == 1:
            parts.append(f"Me falta: {missing[0]}.")
        else:
            parts.append("Me falta: " + ", ".join(missing[:-1]) + f" y {missing[-1]}.")
    parts.extend(errors)
    parts.append("Envíame esas líneas por favor (puedes mandar solo las que faltan).")
    return "\n".join(parts)


def build_summary(data: dict) -> str:
    catastro = (data.get("catastro") or "").strip() or "—"
    email = (data.get("email") or "").strip() or "—"
    pago = "Sí" if data.get("is_pay") else "No"
    return (
        "📋 Resumen del invoice\n"
        f"Cliente:   {data.get('name', '')}\n"
        f"Catastro:  {catastro}\n"
        f"Dirección: {data.get('address', '')}\n"
        f"Email:     {email}\n"
        f"Servicio:  {build_description(data.get('catastro'))}\n"
        f"Monto:     {_fmt_money(data.get('amount'))}\n"
        f"Pago:      {pago}\n\n"
        "¿Lo registro? (sí / no)"
    )


PAYMENT_QUESTION = "¿Está pago? (sí / no)"


# --- Núcleo: un turno del flujo --------------------------------------------
async def handle_incoming_message(chat_id: int, text: str, u_id: str) -> None:
    text = (text or "").strip()
    session = bot_session.load_session(chat_id)

    # ---- Comandos ---------------------------------------------------------
    if text == "/start":
        await telegram_client.send_message(chat_id, WELCOME)
        return

    if text == "/cancelar":
        bot_session.reset_flow(session)
        bot_session.save_session(chat_id, session)
        await telegram_client.send_message(chat_id, "🔄 Cancelado. Cuando quieras, envíame los datos de nuevo.")
        return

    if text.lower() in ("/onai", "/on_ai"):
        if not settings.ANTHROPIC_API_KEY:
            await telegram_client.send_message(
                chat_id, "🤖 Modo AI no configurado (falta ANTHROPIC_API_KEY en el servidor)."
            )
            return
        bot_session.reset_flow(session)
        bot_session.ai_turn_on(session)
        bot_session.save_session(chat_id, session)
        await telegram_client.send_message(
            chat_id,
            f"🤖 Modo AI activado por {settings.AI_MODE_TTL_MINUTES} minutos. "
            "Escríbeme los datos en texto libre. /offAI para apagarlo.",
        )
        return

    if text.lower() in ("/offai", "/off_ai"):
        bot_session.ai_turn_off(session)
        bot_session.reset_flow(session)
        bot_session.save_session(chat_id, session)
        await telegram_client.send_message(chat_id, "🤖 Modo AI desactivado. Vuelvo al formato numerado.")
        return

    # ---- Modo AI (opcional, con expiración) --------------------------------
    if session.get("ai_until"):
        if bot_session.ai_is_active(session):
            from app.services import invoice_agent  # import tardío: solo si se usa

            await invoice_agent.handle_incoming_message(chat_id, text, u_id, session)
            return
        # Expiró: volver a OFF y seguir con el flujo estático
        bot_session.ai_turn_off(session)
        bot_session.reset_flow(session)
        bot_session.save_session(chat_id, session)
        await telegram_client.send_message(
            chat_id, "⏱️ El modo AI expiró; vuelvo al formato numerado."
        )

    # ---- Flujo estático ---------------------------------------------------
    state = session.get("state") or STATE_IDLE
    data = session.get("data") or {}

    if state in (STATE_IDLE, STATE_COLLECTING):
        await _collect(chat_id, session, data, text, first=(state == STATE_IDLE))
        return

    if state == STATE_AWAITING_PAYMENT:
        answer = parse_yes_no(text)
        if answer is None:
            # ¿Mandó una corrección con líneas numeradas? → recolectar de nuevo
            if has_numbered_lines(text):
                await _collect(chat_id, session, data, text, first=False)
                return
            await telegram_client.send_message(chat_id, f"No entendí. {PAYMENT_QUESTION}")
            return
        data["is_pay"] = answer
        session["data"] = data
        session["state"] = STATE_AWAITING_CONFIRM
        bot_session.save_session(chat_id, session)
        await telegram_client.send_message(chat_id, build_summary(data))
        return

    if state == STATE_AWAITING_CONFIRM:
        if has_numbered_lines(text):
            # Corrección: mergear, re-validar y re-resumir (conserva is_pay)
            await _collect(chat_id, session, data, text, first=False, keep_payment=True)
            return
        answer = parse_yes_no(text)
        if answer is None:
            await telegram_client.send_message(
                chat_id,
                "No entendí. ¿Lo registro? (sí / no)\n"
                "Si quieres corregir un dato, repite su línea (ej. \"5. 300\").",
            )
            return
        if answer is False:
            bot_session.reset_flow(session)
            bot_session.save_session(chat_id, session)
            await telegram_client.send_message(chat_id, "❌ Cancelado. No se creó ningún invoice.")
            return

        await telegram_client.send_chat_action(chat_id, "typing")
        created = await bot_invoice.create_and_send(chat_id, u_id, data)
        if created:
            bot_session.reset_flow(session)
            bot_session.save_session(chat_id, session)
        # Si falló, la sesión queda en awaiting_confirm con los datos intactos.
        return

    # Estado desconocido → limpiar y pedir formato
    bot_session.reset_flow(session)
    bot_session.save_session(chat_id, session)
    await telegram_client.send_message(chat_id, FORMAT_HELP)


async def _collect(
    chat_id: int,
    session: dict,
    data: dict,
    text: str,
    first: bool,
    keep_payment: bool = False,
) -> None:
    """Parsea + mergea + valida. Avanza a awaiting_payment (o directo al resumen
    si ya se sabía el estado de pago) o pide lo que falta."""
    incoming = parse_message(text)

    if not incoming:
        if first:
            await telegram_client.send_message(chat_id, FORMAT_HELP)
        else:
            missing, errors = validate(dict(data))
            await telegram_client.send_message(
                chat_id,
                "No reconocí ninguna línea numerada.\n" + build_missing_message(missing, errors),
            )
        return

    data = merge_data(data, incoming)
    missing, errors = validate(data)
    session["data"] = data

    if missing or errors:
        session["state"] = STATE_COLLECTING
        bot_session.save_session(chat_id, session)
        await telegram_client.send_message(chat_id, build_missing_message(missing, errors))
        return

    if keep_payment and "is_pay" in data:
        session["state"] = STATE_AWAITING_CONFIRM
        bot_session.save_session(chat_id, session)
        await telegram_client.send_message(chat_id, build_summary(data))
        return

    session["state"] = STATE_AWAITING_PAYMENT
    bot_session.save_session(chat_id, session)
    await telegram_client.send_message(chat_id, PAYMENT_QUESTION)
