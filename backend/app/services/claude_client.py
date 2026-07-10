# app/services/claude_client.py
"""Cliente mínimo de la Messages API de Anthropic sobre httpx.

A propósito NO usamos el SDK `anthropic`: sus versiones recientes requieren
pydantic v2 y el backend está pineado a `pydantic<2` (ver PLAN §4, Opción A).
Llamamos el endpoint REST directo con httpx —que ya está en requirements— con
los headers `x-api-key` + `anthropic-version`.

El modelo NO se hardcodea: sale de `settings.ANTHROPIC_MODEL` (configurable en
`.env`). Referencia de la API: https://docs.claude.com/en/api/messages
"""
import httpx

from app.core.config import settings

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


async def call_claude(
    system: str,
    messages: list,
    tools: list | None = None,
    max_tokens: int = 1024,
) -> dict:
    """POST /v1/messages y devuelve el JSON de respuesta tal cual.

    - `system`: prompt de sistema (string).
    - `messages`: historial [{"role": ..., "content": ...}].
    - `tools`: lista de definiciones de herramientas, o None.

    El caller inspecciona `resp["stop_reason"]` (`"tool_use"` | `"end_turn"` | ...)
    y `resp["content"]` (lista de bloques `text` / `tool_use`). Deja propagar la
    excepción de httpx en caso de error HTTP para que el agente la maneje.
    """
    headers = {
        "content-type": "application/json",
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
    }
    payload = {
        "model": settings.ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(ANTHROPIC_API_URL, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
