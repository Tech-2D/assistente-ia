from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    app_env: str = "development"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    llm_temperature: float = Field(default=0.7, ge=0, le=2)
    llm_top_p: float = Field(default=0.95, ge=0, le=1)
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    database_statement_timeout_ms: int = Field(default=15000, ge=1000, le=120000)
    firebase_project_id: str = "d-tech-8555e"
    vite_firebase_api_key: str = ""
    vite_firebase_auth_domain: str = ""
    vite_firebase_project_id: str = "d-tech-8555e"
    vite_firebase_app_id: str = ""
    vite_firebase_storage_bucket: str = ""
    vite_firebase_messaging_sender_id: str = ""
    database_url: str = ""
    db_sslrootcert: str = ""
    daily_message_limit: int = Field(default=50, ge=0)
    rate_limit_enabled: bool = True
    rate_limit_db: str = "./work/rate_limits.sqlite3"
    blocked_terms: str = ""
    session_ttl_minutes: int = Field(default=30, ge=1, le=1440)
    max_message_chars: int = Field(default=2000, ge=1, le=10000)


@lru_cache
def get_settings() -> Settings:
    return Settings()
