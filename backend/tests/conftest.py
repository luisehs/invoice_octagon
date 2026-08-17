# backend/tests/conftest.py
"""Stubs para testear el bot sin Supabase, Telegram ni Anthropic.

- `app.db.supabase_client` se reemplaza por un fake en memoria ANTES de importar
  cualquier módulo del bot (el real abre conexión al importar).
- `telegram_client` se parchea para capturar los mensajes enviados.
- `bot_invoice.create_from_bot_data` se parchea para no tocar la BD.
"""
import sys
import types
from datetime import datetime, timezone

import pytest

# --- Fake supabase (solo lo que usa bot_session) ---------------------------
_SESSIONS: dict[int, dict] = {}


class _Resp:
    def __init__(self, data):
        self.data = data


class _Rpc:
    def __init__(self, name, params):
        self.name, self.params = name, params

    def execute(self):
        if self.name == "fn_chat_session_get":
            row = _SESSIONS.get(self.params["p_chat_id"])
            return _Resp(row or {"cs_chat_id": None})
        if self.name == "fn_chat_session_upsert":
            p = self.params
            row = {
                "cs_chat_id": p["p_chat_id"],
                "cs_status": p["p_status"],
                "cs_data": p["p_data"],
                "cs_messages": p["p_messages"],
                "cs_ai_until": p["p_ai_until"],
                "cs_update_at": datetime.now(timezone.utc).isoformat(),
            }
            _SESSIONS[p["p_chat_id"]] = row
            return _Resp(row)
        raise AssertionError(f"RPC inesperado en test: {self.name}")


class _FakeSupabase:
    def rpc(self, name, params):
        return _Rpc(name, params)


fake_mod = types.ModuleType("app.db.supabase_client")
fake_mod.supabase = _FakeSupabase()
sys.modules["app.db.supabase_client"] = fake_mod

# Settings: evitar que BaseSettings exija SUPABASE_URL etc. en el entorno de test
import os  # noqa: E402

os.environ.setdefault("SUPABASE_URL", "http://test")
os.environ.setdefault("SUPABASE_KEY", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test")


@pytest.fixture(autouse=True)
def _clear_sessions():
    _SESSIONS.clear()
    yield
    _SESSIONS.clear()


@pytest.fixture
def sent(monkeypatch):
    """Captura todo lo que el bot 'envía' a Telegram."""
    from app.services import telegram_client

    out: list[dict] = []

    async def send_message(chat_id, text):
        out.append({"type": "message", "chat_id": chat_id, "text": text})
        return {"ok": True}

    async def send_document(chat_id, file_bytes, filename, caption=None):
        out.append({"type": "document", "chat_id": chat_id, "filename": filename, "caption": caption})
        return {"ok": True}

    async def send_chat_action(chat_id, action="typing"):
        return None

    monkeypatch.setattr(telegram_client, "send_message", send_message)
    monkeypatch.setattr(telegram_client, "send_document", send_document)
    monkeypatch.setattr(telegram_client, "send_chat_action", send_chat_action)
    return out


@pytest.fixture
def fake_create(monkeypatch):
    """Reemplaza la creación real por una que devuelve fields/pdf/serie fijos
    y registra los datos recibidos."""
    from app.services import bot_invoice

    calls: list[dict] = []

    def create_from_bot_data(u_id, data):
        calls.append({"u_id": u_id, "data": dict(data)})
        fields = bot_invoice.build_invoice_fields(data, "2026-08-17")
        fields["i_serie"] = "2026-08-17-001"
        return fields, b"%PDF-1.4 fake", "2026-08-17-001"

    monkeypatch.setattr(bot_invoice, "create_from_bot_data", create_from_bot_data)
    return calls
