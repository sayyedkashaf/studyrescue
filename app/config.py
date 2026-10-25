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
SECRET_KEY: str = os.getenv("SECRET_KEY", "")
ENV: str = os.getenv("ENV", "development")
DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

INVITE_CODE: str = os.getenv("INVITE_CODE", "")
EXTRACTION_RATE_LIMIT: int = int(os.getenv("EXTRACTION_RATE_LIMIT", "20"))
MAX_UPLOAD_KB: int = int(os.getenv("MAX_UPLOAD_KB", "200"))

if ENV == "production" and not SECRET_KEY:
    raise RuntimeError("SECRET_KEY missing in production")

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{_project_root / 'data' / 'studyrescue.db'}",
)

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", LLM_MODEL)
DEMO_PASSWORD: str = os.getenv("DEMO_PASSWORD", "")

HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))
