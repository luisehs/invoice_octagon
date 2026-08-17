# app/services/bot_session.py
"""Estado de la conversación del bot, persistido en `chat_sessions` (Supabase).

Una sesión por chat. Forma en memoria (dict):

    {
        "state":    "idle" | "collecting" | "awaiting_payment" | "awaiting_confirm",
        "data":     {name, catastro, address, email, amount, is_pay},   # flujo estático
        "messages": [{role, content}, ...],                             # solo modo AI
        "ai_until": datetime | None,                                    # None = AI OFF
        "update_at": datetime | None,
    }

Requiere haber corrido `supabase_script/telegram_bot.sql` y
`supabase_script/telegram_bot_static.sql`.
"""
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.supabase_client import supabase

STATE_IDLE = "idle"
STATE_COLLECTING = "collecting"
STATE_AWAITING_PAYMENT = "awaiting_payment"
STATE_AWAITING_CONFIRM = "awaiting_confirm"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        # Supabase devuelve ISO-8601, a veces con 'Z'
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def empty_session() -> dict:
    return {
        "state": STATE_IDLE,
        "data": {},
        "messages": [],
        "ai_until": None,
        "update_at": None,
    }


def load_session(chat_id: int) -> dict:
    """Carga la sesión del chat. Si no existe, o quedó abandonada más de
    SESSION_TTL_MINUTES, devuelve una sesión limpia (conservando ai_until solo
    si sigue vigente)."""
    try:
        resp = supabase.rpc("fn_chat_session_get", {"p_chat_id": chat_id}).execute()
    except Exception as exc:
        print(f"[session] error en fn_chat_session_get: {exc}")
        return empty_session()

    row = resp.data
    if isinstance(row, list):
        row = row[0] if row else None
    if not row or row.get("cs_chat_id") is None:
        return empty_session()

    session = {
        "state": row.get("cs_status") or STATE_IDLE,
        "data": row.get("cs_data") or {},
        "messages": row.get("cs_messages") or [],
        "ai_until": _parse_ts(row.get("cs_ai_until")),
        "update_at": _parse_ts(row.get("cs_update_at")),
    }

    # Sesión abandonada → se reinicia sola (pero el modo AI vigente se respeta).
    ttl = timedelta(minutes=settings.SESSION_TTL_MINUTES)
    if session["update_at"] and _now() - session["update_at"] > ttl:
        fresh = empty_session()
        fresh["ai_until"] = session["ai_until"] if ai_is_active(session) else None
        return fresh

    return session


def save_session(chat_id: int, session: dict) -> None:
    ai_until = session.get("ai_until")
    try:
        supabase.rpc(
            "fn_chat_session_upsert",
            {
                "p_chat_id": chat_id,
                "p_status": session.get("state") or STATE_IDLE,
                "p_data": session.get("data") or {},
                "p_messages": session.get("messages") or [],
                "p_ai_until": ai_until.isoformat() if ai_until else None,
            },
        ).execute()
    except Exception as exc:
        print(f"[session] error en fn_chat_session_upsert: {exc}")


def reset_flow(session: dict) -> dict:
    """Vuelve el flujo a idle sin tocar el modo AI."""
    session["state"] = STATE_IDLE
    session["data"] = {}
    session["messages"] = []
    return session


def reset_session(chat_id: int) -> None:
    """Sesión completamente limpia (idle, sin datos, AI OFF)."""
    save_session(chat_id, empty_session())


# --- Modo AI ---------------------------------------------------------------
def ai_is_active(session: dict) -> bool:
    until = session.get("ai_until")
    return bool(until) and until > _now()


def ai_turn_on(session: dict) -> datetime:
    until = _now() + timedelta(minutes=settings.AI_MODE_TTL_MINUTES)
    session["ai_until"] = until
    session["messages"] = []
    return until


def ai_turn_off(session: dict) -> None:
    session["ai_until"] = None
    session["messages"] = []
