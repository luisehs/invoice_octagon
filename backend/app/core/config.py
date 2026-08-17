# app/core/config.py
from pydantic import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Fase 2 — bot de Telegram (opcionales: el API principal arranca sin ellas)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"
    # Modo AI (/onAI): minutos que dura encendido antes de volver a OFF solo.
    AI_MODE_TTL_MINUTES: int = 30
    # Sesión del bot abandonada por más de N minutos → arranca limpia.
    SESSION_TTL_MINUTES: int = 120

    class Config:
        env_file = ".env"


settings = Settings()
