# backend/tests/test_bot_flow.py
"""Flujo estático end-to-end con Supabase/Telegram/creación stubbeados."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services import bot_flow, bot_session

CHAT = 123
UID = "00000000-0000-0000-0000-000000000001"

EXAMPLE = """Saludos:
1. Francisco J Olivencia Torres
2.Catastro: 023–035-213-08
3.246 Calle Andalucía Aguadilla PR 00603
4. Email: folivencia.torres"""


def run(text):
    return asyncio.run(bot_flow.handle_incoming_message(CHAT, text, UID))


def last(sent):
    return sent[-1]["text"] if sent[-1]["type"] == "message" else sent[-1]


def test_full_happy_path(sent, fake_create):
    run(EXAMPLE)
    assert "5. monto" in last(sent) and "folivencia.torres" in last(sent)
    assert bot_session.load_session(CHAT)["state"] == "collecting"

    run("5. $250\n4. folivencia.torres@gmail.com")
    assert last(sent) == bot_flow.PAYMENT_QUESTION
    assert bot_session.load_session(CHAT)["state"] == "awaiting_payment"

    run("no")
    summary = last(sent)
    assert "Appraisal Report - Catastro 023-035-213-08" in summary
    assert "$250.00" in summary and "Pago:      No" in summary and "¿Lo registro?" in summary

    run("sí")
    doc = sent[-1]
    assert doc["type"] == "document"
    assert doc["filename"] == "invoice_2026-08-17-001.pdf"
    assert "Pendiente" in doc["caption"] and "$250.00" in doc["caption"]

    assert len(fake_create) == 1
    d = fake_create[0]["data"]
    assert d["name"] == "Francisco J Olivencia Torres"
    assert d["amount"] == 250.0 and d["is_pay"] is False
    assert fake_create[0]["u_id"] == UID
    assert bot_session.load_session(CHAT)["state"] == "idle"


def test_plain_text_in_idle_shows_help(sent):
    run("hola")
    assert last(sent) == bot_flow.FORMAT_HELP


def test_only_required_and_paid(sent, fake_create):
    run("1. Ana Ríos\n3. Calle Sol 5 Mayagüez PR\n5. 300")
    assert last(sent) == bot_flow.PAYMENT_QUESTION
    run("sí")
    assert "Servicio:  Appraisal Report\n" in last(sent)
    assert "Catastro:  —" in last(sent) and "Email:     —" in last(sent)
    run("si")
    assert sent[-1]["type"] == "document" and "Pagado" in sent[-1]["caption"]
    assert fake_create[0]["data"]["is_pay"] is True


def test_correction_in_confirm(sent, fake_create):
    run("1. Ana\n3. Calle X\n5. 100")
    run("no")
    run("5. 150")  # corrección → re-resumen conservando pago
    assert "$150.00" in last(sent) and "¿Lo registro?" in last(sent)
    run("sí")
    assert fake_create[0]["data"]["amount"] == 150.0


def test_decline_confirm(sent, fake_create):
    run("1. Ana\n3. Calle X\n5. 100")
    run("no")
    run("no")
    assert "Cancelado" in last(sent)
    assert fake_create == []
    assert bot_session.load_session(CHAT)["state"] == "idle"


def test_cancel_command(sent):
    run("1. Ana")
    run("/cancelar")
    assert "Cancelado" in last(sent)
    assert bot_session.load_session(CHAT)["data"] == {}


def test_creation_error_keeps_session(sent, monkeypatch):
    from app.services import bot_invoice

    def boom(u_id, data):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(bot_invoice, "create_from_bot_data", boom)
    run("1. Ana\n3. Calle X\n5. 100")
    run("no")
    run("sí")
    assert "error" in last(sent).lower()
    s = bot_session.load_session(CHAT)
    assert s["state"] == "awaiting_confirm" and s["data"]["name"] == "Ana"


def test_onai_without_key(sent, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    run("/onAI")
    assert "no configurado" in last(sent)
    assert bot_session.load_session(CHAT)["ai_until"] is None


def test_onai_delegates_and_expires(sent, monkeypatch):
    from app.core.config import settings
    from app.services import invoice_agent

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    calls = []

    async def fake_agent(chat_id, text, u_id, session):
        calls.append(text)

    monkeypatch.setattr(invoice_agent, "handle_incoming_message", fake_agent)

    run("/onAI")
    assert "activado" in last(sent)
    run("crea un invoice para Juan")
    assert calls == ["crea un invoice para Juan"]

    # Simular expiración
    s = bot_session.load_session(CHAT)
    s["ai_until"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    bot_session.save_session(CHAT, s)
    run("hola")
    assert any("expiró" in m["text"] for m in sent if m["type"] == "message")
    assert last(sent) == bot_flow.FORMAT_HELP
    assert bot_session.load_session(CHAT)["ai_until"] is None
    assert calls == ["crea un invoice para Juan"]  # no volvió a llamar al agente


def test_offai(sent, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    run("/onAI")
    run("/offAI")
    assert "desactivado" in last(sent)
    assert bot_session.load_session(CHAT)["ai_until"] is None


def test_build_invoice_fields_mapping():
    from app.services.bot_invoice import build_invoice_fields, ISSUER_NAME

    f = build_invoice_fields(
        {"name": "Ana", "address": "Calle X", "amount": 250.0, "catastro": "1-2", "is_pay": True},
        "2026-08-17",
    )
    assert f["i_name"] == ISSUER_NAME
    assert f["i_billto"] == "Ana"
    assert f["i_total"] == 250.0 and f["i_is_pay"] is True
    d = f["details"][0]
    assert d["id_description"] == "Appraisal Report - Catastro 1-2"
    assert d["id_qty"] == 1 and d["id_rate"] == 250.0 and d["id_adress"] == "Calle X"
