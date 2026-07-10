# backend/scripts/set_webhook.py
"""Registra / borra / inspecciona el webhook de Telegram.

Correr desde `backend/` (para que cargue `.env` y `app`):

    python scripts/set_webhook.py set https://api.octagonpr.co/telegram/webhook
    python scripts/set_webhook.py info
    python scripts/set_webhook.py delete

`set` pasa el `secret_token` (TELEGRAM_WEBHOOK_SECRET) que luego el webhook valida
en cada request vía el header X-Telegram-Bot-Api-Secret-Token. Recuerda: webhook y
long polling son excluyentes — al registrar el webhook, deja de correr bot_polling.
"""
import asyncio
import os
import sys

# Permite `python scripts/set_webhook.py ...` (agrega backend/ al path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services import telegram_client  # noqa: E402

BASE = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


async def do_set(url: str) -> None:
    if not settings.TELEGRAM_WEBHOOK_SECRET:
        raise SystemExit("Falta TELEGRAM_WEBHOOK_SECRET en backend/.env")
    res = await telegram_client.set_webhook(url, settings.TELEGRAM_WEBHOOK_SECRET)
    print("setWebhook →", res)
    await do_info()


async def do_delete() -> None:
    res = await telegram_client.delete_webhook()
    print("deleteWebhook →", res)


async def do_info() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE}/getWebhookInfo")
        info = r.json()
    print("getWebhookInfo →", info)
    result = (info or {}).get("result", {})
    if result.get("last_error_message"):
        print(f"  ⚠️ last_error_message: {result['last_error_message']}")


def main() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en backend/.env")

    args = sys.argv[1:]
    cmd = args[0] if args else "info"

    if cmd == "set":
        if len(args) < 2:
            raise SystemExit(
                "Uso: python scripts/set_webhook.py set https://<dominio>/telegram/webhook"
            )
        asyncio.run(do_set(args[1]))
    elif cmd == "delete":
        asyncio.run(do_delete())
    elif cmd == "info":
        asyncio.run(do_info())
    else:
        raise SystemExit(f"Comando desconocido: {cmd}. Usa: set | delete | info")


if __name__ == "__main__":
    main()
