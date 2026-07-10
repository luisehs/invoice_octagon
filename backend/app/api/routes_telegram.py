# app/api/routes_telegram.py
"""Webhook de Telegram (Fase E).

    POST /telegram/webhook

- Valida el header `X-Telegram-Bot-Api-Secret-Token` contra
  `settings.TELEGRAM_WEBHOOK_SECRET` (si no coincide → 403).
- Parsea el update; ignora todo lo que no sea `message.text` de un chat privado
  (a fotos/audios responde "solo texto").
- Procesa el mensaje con `BackgroundTasks` y **responde 200 de inmediato**:
  Telegram reintenta si no recibe 200 rápido, y la cadena Claude+PDF puede tardar
  >10 s. Reutiliza el mismo `handle_incoming_message` que el long polling.

Nota (§0.1.6): un error del bot nunca debe tumbar la respuesta. El handler ya
captura sus propios errores; además corre en background, después del 200.
"""
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from app.core.config import settings
from app.services import telegram_client
# Reutilizamos el router de mensajes del runner de polling (comandos + whitelist
# + /register + delegación al agente). Importarlo NO arranca el loop de polling.
from app.bot_polling import handle_incoming_message

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    # 1. Validar el secret token. Si no está configurado, el webhook está cerrado.
    if (
        not settings.TELEGRAM_WEBHOOK_SECRET
        or x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret token"
        )

    # 2. Parsear el update (siempre respondemos 200; un update inválido se ignora).
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id is None or chat.get("type") != "private":
        return {"ok": True}

    text = message.get("text")
    if text is None:
        # Foto / audio / etc. — v1 solo texto.
        background_tasks.add_task(
            telegram_client.send_message, chat_id, "Por ahora solo proceso texto. 🙏"
        )
        return {"ok": True}

    # 3. Procesar en background y devolver 200 YA.
    background_tasks.add_task(handle_incoming_message, chat_id, text)
    return {"ok": True}
