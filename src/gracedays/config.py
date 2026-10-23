from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load the conventional project .env first, then src/.env (the current scaffold
# stores its example alongside src/pyproject.toml). Existing shell variables win.
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[2]
_SRC_ROOT = _THIS_FILE.parents[1]
load_dotenv(_PROJECT_ROOT / ".env", override=False)
load_dotenv(_SRC_ROOT / ".env", override=False)
load_dotenv(override=False)


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "GraceDays"
    timezone: str = "Asia/Kolkata"
    fake_today: str | None = None
    max_source_text_chars: int = 20_000
    llm_provider: str = "mock"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 30.0
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001
    mcp_server_url: str = "http://127.0.0.1:8001/mcp"
    turso_database_url: str | None = None
    turso_auth_token: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        raw_fake_today = os.getenv("APP_FAKE_TODAY", "").strip() or None
        settings = cls(
            app_name=os.getenv("APP_NAME", "GraceDays").strip() or "GraceDays",
            timezone=os.getenv("APP_TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata",
            fake_today=raw_fake_today,
            max_source_text_chars=int(os.getenv("MAX_SOURCE_TEXT_CHARS", "20000")),
            llm_provider=os.getenv("LLM_PROVIDER", "mock").strip().lower(),
            llm_api_key=os.getenv("LLM_API_KEY", "").strip() or None,
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini").strip(),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
            mcp_host=os.getenv("MCP_HOST", "127.0.0.1").strip(),
            mcp_port=int(os.getenv("MCP_PORT", "8001")),
            mcp_server_url=os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp").strip(),
            turso_database_url=os.getenv("TURSO_DATABASE_URL", "").strip() or None,
            turso_auth_token=os.getenv("TURSO_AUTH_TOKEN", "").strip() or None,
        )
        if settings.max_source_text_chars < 100:
            raise ValueError("MAX_SOURCE_TEXT_CHARS must be at least 100")
        if settings.llm_provider not in {"mock", "openai_compatible"}:
            raise ValueError("LLM_PROVIDER must be 'mock' or 'openai_compatible'")
        if settings.llm_provider != "mock" and not settings.llm_api_key:
            raise ValueError("LLM_API_KEY is required for a live provider; use LLM_PROVIDER=mock for offline mode")
        if settings.mcp_port not in range(1, 65536):
            raise ValueError("MCP_PORT must be a valid TCP port")
        if bool(settings.turso_database_url) != bool(settings.turso_auth_token):
            raise ValueError("Set both TURSO_DATABASE_URL and TURSO_AUTH_TOKEN, or leave both unset")
        return settings

    def repository_root(self) -> Path:
        # Archive contains src/ and data/ as siblings.
        return Path(__file__).resolve().parents[2]


def load_settings() -> Settings:
    """Backward-compatible settings loader used by tests and local scripts."""
    return Settings.from_env()
