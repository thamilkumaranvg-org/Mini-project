"""Application configuration loaded from environment variables using pydantic-settings."""
from typing import Optional
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import sys

_backend_env = Path(__file__).resolve().parent.parent / ".env"
_root_env = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    APP_ENV: str = Field(default="development")
    APP_BASE_URL: str = Field(default="http://localhost:8000")

    SUPABASE_URL: str = Field(...)
    SUPABASE_ANON_KEY: str = Field(...)
    SUPABASE_SERVICE_ROLE_KEY: str = Field(...)

    COOKIE_SECURE: bool = Field(default=False)
    TIMEZONE: str = Field(default="Asia/Kolkata")
    BOOKING_WINDOW_DAYS: int = Field(default=7)
    ALMOST_FULL_THRESHOLD: int = Field(default=2)
    BOOKING_CLOSE_MINUTES_BEFORE_END: int = Field(default=0)
    CHECKIN_OPEN_MINUTES_BEFORE: int = Field(default=0)
    MAX_QUANTITY_KG: float = Field(default=10000.0)

    TIME_OVERRIDE_ISO: Optional[str] = Field(default=None)

    EMAIL_PROVIDER: str = Field(default="console")  # console, resend, smtp
    EMAIL_FROM: str = Field(default="no-reply@farmerslotbooking.gov.in")
    RESEND_API_KEY: Optional[str] = Field(default=None)

    SMTP_HOST: Optional[str] = Field(default=None)
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: Optional[str] = Field(default=None)
    SMTP_PASSWORD: Optional[str] = Field(default=None)

    ADMIN_EMAIL: str = Field(default="admin@slotbooking.gov.in")
    ADMIN_PASSWORD: str = Field(default="AdminSecurePassword123!")
    ADMIN_FULL_NAME: str = Field(default="Super Administrator")

    LOGIN_RATE_LIMIT: str = Field(default="10/minute")

    model_config = SettingsConfigDict(
        env_file=(_backend_env, _root_env, ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        if v.lower() not in ("development", "production", "test"):
            raise ValueError("APP_ENV must be 'development', 'production', or 'test'")
        return v.lower()

    @field_validator("EMAIL_PROVIDER")
    @classmethod
    def validate_email_provider(cls, v: str) -> str:
        if v.lower() not in ("console", "resend", "smtp"):
            raise ValueError("EMAIL_PROVIDER must be 'console', 'resend', or 'smtp'")
        return v.lower()


try:
    settings = Settings()
except Exception as e:
    print(f"\n[FATAL CONFIG ERROR] Failed to load configuration: {e}\n", file=sys.stderr)
    raise SystemExit(1) from e
