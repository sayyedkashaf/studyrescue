"""
Application configuration.
Reads all settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level above app/)
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

# ── Application ──────────────────────────────────────────────────────
APP_NAME: str = os.getenv("APP_NAME", "Study Rescue")
SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE-ME")
DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

# ── Database ─────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{_project_root / 'data' / 'studyrescue.db'}",
)

# ── LLM ──────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")

# ── Server ───────────────────────────────────────────────────────────
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))
