"""Application settings. Every secret comes from the environment (or Azure Key Vault-injected env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "Football Intelligence OS"
    environment: str = "local"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5188", "http://127.0.0.1:5188"])

    # Azure OpenAI / Microsoft Foundry
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4.1-mini"
    azure_openai_deployment_large: str = ""
    azure_openai_api_version: str = "2025-03-01-preview"
    azure_openai_embedding_deployment: str = ""

    # Azure AI Speech
    azure_speech_key: str = ""
    azure_speech_region: str = "eastus"
    azure_speech_voice: str = "en-US-AvaMultilingualNeural"

    # Azure AI Document Intelligence
    azure_doc_intel_endpoint: str = ""
    azure_doc_intel_key: str = ""

    # Data
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "football_os"
    # "local" = numpy cosine over stored vectors; "atlas" = $vectorSearch; "cosmos" = cosmosSearch (vCore)
    vector_backend: str = "local"
    redis_url: str = ""

    # Pipeline tuning
    significance_threshold: float = 0.25
    large_model_threshold: float = 0.7
    worker_concurrency: int = 8
    context_ttl_seconds: int = 7200
    insight_cache_ttl_seconds: int = 7 * 24 * 3600  # real-match events are immutable → insights stay valid
    llm_timeout_seconds: float = 20.0

    # Security
    auth_jwt_issuer: str = ""
    auth_jwt_audience: str = ""
    api_keys: str = ""  # comma-separated; empty = demo mode (no auth)
    rate_limit_per_minute: int = 240

    @property
    def llm_enabled(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)

    @property
    def speech_enabled(self) -> bool:
        return bool(self.azure_speech_key and self.azure_speech_region)

    @property
    def doc_intel_enabled(self) -> bool:
        return bool(self.azure_doc_intel_endpoint and self.azure_doc_intel_key)

    @property
    def large_deployment(self) -> str:
        return self.azure_openai_deployment_large or self.azure_openai_deployment

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
