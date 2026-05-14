"""
Application settings loaded from environment / .env.

Uses pydantic-settings so each field is typed, validated on startup, and
missing values surface as a clear pydantic ValidationError instead of a
generic "Missing required environment variables" string.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    serpapi_key: str
    database_url: str
    trigger_token: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
