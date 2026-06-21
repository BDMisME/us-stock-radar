"""Central configuration loaded from environment / .env.

All secrets and tunables flow through here so the rest of the codebase never
reads os.environ directly. Missing keys are allowed (the app degrades
gracefully) — use the ``*_enabled`` helpers to gate functionality.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = parent of the config/ directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env once, from the project root, before Settings reads the environment.
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """Typed view over environment configuration."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,  # treat SMTP_PORT= (empty) as unset → use default
    )

    # Alpaca
    alpaca_api_key: str = Field(default="", alias="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(default="", alias="ALPACA_SECRET_KEY")

    # Backup providers
    finnhub_api_key: str = Field(default="", alias="FINNHUB_API_KEY")
    fmp_api_key: str = Field(default="", alias="FMP_API_KEY")

    # LLM (any OpenAI-compatible provider — OpenAI, Groq, Gemini, Volcengine ARK, etc.)
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_model: str = Field(default="", alias="LLM_MODEL")

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    # Email
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=0, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    email_to: str = Field(default="", alias="EMAIL_TO")

    # Database
    db_path: str = Field(default="./db/us_stock_radar.sqlite", alias="DB_PATH")

    # Tunables
    watchlist_poll_seconds: int = Field(default=5, alias="WATCHLIST_POLL_SECONDS")
    ai_worker_interval_seconds: int = Field(default=30, alias="AI_WORKER_INTERVAL_SECONDS")
    alert_worker_interval_seconds: int = Field(default=15, alias="ALERT_WORKER_INTERVAL_SECONDS")

    # AI cooldown (per category, in hours)
    ai_cooldown_core_hours: int = Field(default=2, alias="AI_COOLDOWN_CORE_HOURS")
    ai_cooldown_focus_hours: int = Field(default=4, alias="AI_COOLDOWN_FOCUS_HOURS")

    app_credit_name: str = Field(default="", alias="APP_CREDIT_NAME")

    # ---- capability gates -------------------------------------------------
    @property
    def alpaca_enabled(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    @property
    def finnhub_enabled(self) -> bool:
        return bool(self.finnhub_api_key)

    @property
    def fmp_enabled(self) -> bool:
        return bool(self.fmp_api_key)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_port and self.email_to)

    @property
    def db_file(self) -> Path:
        """Absolute path to the SQLite file (relative paths resolved to root)."""
        p = Path(self.db_path)
        return p if p.is_absolute() else (PROJECT_ROOT / p)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
