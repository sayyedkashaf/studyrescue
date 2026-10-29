"""
Application configuration.
Reads all settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

APP_NAME: str = os.getenv("APP_NAME", "Study Rescue")
SECRET_KEY: str = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET") or "studyrescue-default-secret-key-at-least-32-chars"
ENV: str = os.getenv("ENV", "development")
DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

INVITE_CODE: str = os.getenv("INVITE_CODE", "")
EXTRACTION_RATE_LIMIT: int = int(os.getenv("EXTRACTION_RATE_LIMIT", "20"))
MAX_UPLOAD_KB: int = int(os.getenv("MAX_UPLOAD_KB", "200"))

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{_project_root / 'data' / 'studyrescue.db'}",
)

# ── Session / Cookie configuration ─────────────────────────────────────
SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "studyrescue_session")
SESSION_COOKIE_DOMAIN: str | None = os.getenv("SESSION_COOKIE_DOMAIN", None) or None
_is_prod = ENV == "production" or bool(os.getenv("RENDER"))
SESSION_COOKIE_SECURE: bool = os.getenv(
    "SESSION_COOKIE_SECURE", "true" if _is_prod else "false"
).lower() in ("true", "1", "yes")
SESSION_COOKIE_SAMESITE: str = os.getenv(
    "SESSION_COOKIE_SAMESITE", "none" if _is_prod else "lax"
)  # lax | none | strict
SESSION_MAX_AGE_SECONDS: int = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(60 * 60 * 24 * 14)))
CSRF_MAX_AGE_SECONDS: int = int(os.getenv("CSRF_MAX_AGE_SECONDS", str(60 * 60 * 2)))

# ── CORS / Cross-origin configuration ──────────────────────────────────
CORS_ENABLED: bool = os.getenv("CORS_ENABLED", "false").lower() in ("true", "1", "yes")
CORS_ALLOW_ORIGINS: list[str] = [
    o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()
]
CORS_ALLOW_CREDENTIALS: bool = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() in ("true", "1", "yes")
FRONTEND_URL: str | None = os.getenv("FRONTEND_URL", None) or None

# ── LLM configuration ──────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-3.1-flash-lite")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", LLM_MODEL)
DEMO_PASSWORD: str = os.getenv("DEMO_PASSWORD", "")

# ── Server ─────────────────────────────────────────────────────────────
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))
