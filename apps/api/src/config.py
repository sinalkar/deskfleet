"""Centralized configuration via pydantic-settings.

Nothing else in the codebase reads ``os.environ`` directly — everything imports
``settings`` from here. Values load from the process environment and an optional
``.env`` file. All fields have safe defaults so the app (and the test suite) can
boot with **zero** secrets configured.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── LLM ──
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    temperature: float = 0.2

    # ── LangSmith ──
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "deskfleet"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # ── External order API ──
    fakestore_base_url: str = "https://fakestoreapi.com"
    http_timeout_seconds: float = 10.0

    # ── Agent behavior ──
    max_review_iterations: int = 2
    max_tool_rounds: int = 3

    # ── Storage ──
    sqlite_path: str = "./deskfleet.db"

    # ── Service ──
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    log_level: str = "INFO"

    # ── UI ──
    api_url: str = "http://localhost:8080"

    @property
    def has_llm_credentials(self) -> bool:
        """True when a real OpenAI-compatible key is configured."""
        return bool(self.openai_api_key and self.openai_api_key != "sk-...")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
