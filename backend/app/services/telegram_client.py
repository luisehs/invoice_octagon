# app/services/telegram_client.py
"""Salida hacia la Bot API de Telegram (api.telegram.org) con httpx async.

Módulo compartido: lo usa `bot_polling.py` (dev, Fase B) y lo usará el webhook
de `routes_telegram.py` (Fase E). Todo async para encajar con FastAPI. Cada
llamada abre un cliente httpx corto — el volumen del bot es bajo (un usuario).
"""
import httpx

from app.core.config import settings

API_BASE = "https://api.telegram.org"


def _base_url() -> str:
    return f"{API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}"


async def send_message(chat_id: int, text: str) -> dict:
    """Envía un mensaje de texto al chat."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_base_url()}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        resp.raise_for_status()
        return resp.json()


async def send_document(
    chat_id: int,
    file_bytes: bytes,
    filename: str,
    caption: str | None = None,
) -> dict:
    """Sube un archivo (PDF del invoice) vía multipart a sendDocument."""
    data: dict = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption
    files = {"document": (filename, file_bytes, "application/pdf")}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{_base_url()}/sendDocument",
            data=data,
            files=files,
        )
        resp.raise_for_status()
        return resp.json()


async def send_chat_action(chat_id: int, action: str = "typing") -> dict | None:
    """Feedback tipo "escribiendo…" mientras se procesa. Best-effort: si falla,
    no rompe el flujo (devuelve None)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_base_url()}/sendChatAction",
                json={"chat_id": chat_id, "action": action},
            )
            return resp.json()
    except Exception:
        return None


async def set_webhook(url: str, secret_token: str) -> dict:
    """Registra el webhook (Fase E). `secret_token` se valida en cada request
    entrante vía el header X-Telegram-Bot-Api-Secret-Token."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_base_url()}/setWebhook",
            json={"url": url, "secret_token": secret_token},
        )
        resp.raise_for_status()
        return resp.json()


async def delete_webhook() -> dict:
    """Borra el webhook. Necesario antes de usar long polling (son excluyentes)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{_base_url()}/deleteWebhook")
        resp.raise_for_status()
        return resp.json()
