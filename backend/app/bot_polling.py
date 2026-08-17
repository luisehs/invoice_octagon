# app/bot_polling.py
"""Runner de desarrollo: long polling contra Telegram.

Uso (desde backend/):   python -m app.bot_polling

- Borra el webhook al arrancar (webhook y polling son excluyentes en Telegram).
- /id y /register funcionan para cualquiera (no requieren whitelist).
- /register pide email + contraseña de la cuenta de la app y los valida con la
  MISMA lógica que el login web (verify_password). Si son correctos, vincula el
  chat al u_id autenticado (se auto-registra en la whitelist).
- Cualquier otro texto exige estar en telegram_users (whitelist). Si no estás,
  responde "no autorizado" e invita a usar /register.
- Para usuarios whitelisted todo lo demás (comandos del flujo, /onAI, /offAI,
  formato numerado) lo maneja `services/bot_flow.py` (flujo ESTÁTICO).

El mismo `handle_incoming_message` lo reutiliza el webhook (routes_telegram).
NOTA: el estado del flujo /register vive en memoria (dict de abajo). Sirve para
el polling de dev; para el webhook (Fase E, multi-proceso) habrá que persistirlo.
"""
import asyncio

import httpx

from app.core.config import settings
from app.core.security import verify_password
from app.db.supabase_client import supabase
from app.services import bot_flow, bot_session, telegram_client

# Estado en memoria del flujo /register (chat_id -> {"step": "email"|"password", ...}).
# Solo para el runner de polling; se pierde al reiniciar (basta con re-hacer /register).
_pending_register: dict[int, dict] = {}


def get_telegram_user(chat_id: int) -> dict | None:
    """Devuelve la fila de telegram_users si el chat está whitelisted y activo,
    o None. fn_telegram_user_get devuelve un registro all-null cuando no hay
    match, así que lo detectamos por tu_u_id."""
    try:
        resp = supabase.rpc("fn_telegram_user_get", {"p_chat_id": chat_id}).execute()
    except Exception as exc:
        print(f"[whitelist] error consultando fn_telegram_user_get: {exc}")
        return None

    data = resp.data
    if isinstance(data, list):
        data = data[0] if data else None
    if data and data.get("tu_u_id"):
        return data
    return None


def reset_session(chat_id: int) -> None:
    """Sesión limpia (idle, sin datos, AI OFF)."""
    bot_session.reset_session(chat_id)


def authenticate_user(email: str, password: str) -> dict | None:
    """Valida email + contraseña con la MISMA lógica que /auth/login: busca el
    usuario por email y compara con verify_password (bcrypt_sha256). Devuelve la
    fila del usuario si son correctos, o None."""
    email = (email or "").strip()
    try:
        resp = (
            supabase.table("users")
            .select("*")
            .eq("u_email", email)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        print(f"[register] error buscando usuario: {exc}")
        return None

    user = resp.data[0] if resp.data else None
    if not user:
        return None
    try:
        if not verify_password(password, user["u_password"]):
            return None
    except Exception as exc:
        print(f"[register] error verificando contraseña: {exc}")
        return None
    return user


def register_chat(chat_id: int, u_id: str, name: str | None = None) -> bool:
    """Vincula (o reactiva) el chat en la whitelist mapeándolo a u_id."""
    try:
        supabase.rpc(
            "fn_telegram_user_upsert",
            {"p_chat_id": chat_id, "p_u_id": u_id, "p_name": name},
        ).execute()
        return True
    except Exception as exc:
        print(f"[register] error en fn_telegram_user_upsert: {exc}")
        return False


async def handle_incoming_message(chat_id: int, text: str) -> None:
    """Procesa un mensaje de texto entrante. Mismo handler para polling y webhook."""
    text = (text or "").strip()

    # /id: disponible para cualquiera
    if text == "/id":
        await telegram_client.send_message(chat_id, f"🆔 Tu chat_id es: {chat_id}")
        return

    # /cancelar a mitad de /register: aborta el registro (antes de whitelist).
    # Si ya está whitelisted, lo maneja bot_flow (resetea solo el flujo).
    if text == "/cancelar" and chat_id in _pending_register:
        _pending_register.pop(chat_id, None)
        await telegram_client.send_message(chat_id, "🔄 Registro cancelado.")
        return

    # /register: inicia el flujo email -> contraseña (no requiere whitelist)
    if text == "/register":
        if get_telegram_user(chat_id):
            await telegram_client.send_message(chat_id, "✅ Ya estás registrado.")
            return
        _pending_register[chat_id] = {"step": "email"}
        await telegram_client.send_message(
            chat_id, "🔐 Registro. Envía el email de tu cuenta de la app:"
        )
        return

    # Pasos intermedios del registro (estado en memoria)
    pending = _pending_register.get(chat_id)
    if pending is not None:
        if pending["step"] == "email":
            pending["email"] = text
            pending["step"] = "password"
            await telegram_client.send_message(chat_id, "Ahora envía tu contraseña:")
            return
        if pending["step"] == "password":
            email = pending.get("email", "")
            _pending_register.pop(chat_id, None)
            user = authenticate_user(email, text)
            if not user:
                await telegram_client.send_message(
                    chat_id,
                    "❌ Email o contraseña incorrectos. Usa /register para reintentar.",
                )
                return
            if register_chat(chat_id, user["u_id"], user.get("u_firstname")):
                await telegram_client.send_message(
                    chat_id, f"✅ Registrado como {email}. Ya puedes usar el bot."
                )
            else:
                await telegram_client.send_message(
                    chat_id, "⚠️ Error guardando el registro. Intenta de nuevo."
                )
            return

    # Whitelist: todo lo demás exige autorización
    user = get_telegram_user(chat_id)
    if not user:
        await telegram_client.send_message(
            chat_id,
            f"🚫 No autorizado.\nTu chat_id es {chat_id}. "
            "Usa /register para vincular tu cuenta.",
        )
        return

    # Flujo estático (+ /onAI opcional): comandos, formato numerado, creación.
    await bot_flow.handle_incoming_message(chat_id, text, user["tu_u_id"])


async def poll() -> None:
    # Telegram: webhook y polling son excluyentes → asegurar que no haya webhook
    try:
        await telegram_client.delete_webhook()
    except Exception as exc:
        print(f"[polling] no se pudo borrar el webhook (¿token?): {exc}")

    print("Bot en modo long polling. Ctrl-C para salir.")
    offset: int | None = None
    base = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

    async with httpx.AsyncClient(timeout=40) as client:
        while True:
            params: dict = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset

            try:
                resp = await client.get(f"{base}/getUpdates", params=params)
                resp.raise_for_status()
                updates = resp.json().get("result", [])
            except Exception as exc:
                print(f"[polling] getUpdates error: {exc}")
                await asyncio.sleep(3)
                continue

            for upd in updates:
                offset = upd["update_id"] + 1
                message = upd.get("message") or upd.get("edited_message")
                if not message:
                    continue

                chat = message.get("chat", {})
                chat_id = chat.get("id")
                if chat_id is None or chat.get("type") != "private":
                    continue

                text = message.get("text")
                if text is None:
                    # Foto / audio / etc. — v1 solo texto
                    try:
                        await telegram_client.send_message(
                            chat_id, "Por ahora solo proceso texto. 🙏"
                        )
                    except Exception as exc:
                        print(f"[polling] error respondiendo no-texto: {exc}")
                    continue

                try:
                    await handle_incoming_message(chat_id, text)
                except Exception as exc:
                    print(f"[polling] error en handler (chat {chat_id}): {exc}")


def main() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en backend/.env")
    try:
        asyncio.run(poll())
    except KeyboardInterrupt:
        print("\nBot detenido.")


if __name__ == "__main__":
    main()
