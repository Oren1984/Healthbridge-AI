"""Environment-based configuration. All settings use the HB_ prefix."""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HB_", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://healthbridge:healthbridge@db:5432/healthbridge"

    # Document storage (files are Fernet-encrypted at rest)
    storage_dir: str = "/data/documents"
    storage_encryption_key: str = Field(min_length=32)
    max_upload_bytes: int = 10 * 1024 * 1024

    # Sessions / cookies
    session_ttl_minutes: int = 480
    cookie_secure: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]

    # Audit integrity chain
    audit_hmac_key: str = Field(min_length=16)

    # LiveKit
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_public_url: str = "ws://localhost:7880"
    livekit_internal_url: str = "http://livekit:7880"
    livekit_token_ttl_seconds: int = 600

    # AI
    ai_mode: Literal["mock", "ollama"] = "mock"
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: float = 45.0
    embedding_provider: Literal["hash", "fastembed"] = "hash"
    fastembed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # Demo
    demo_mode: bool = True

    # Worker
    worker_poll_seconds: float = 3.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
