"""
Study Rescue – FastAPI application entry point.

Phase 1: project skeleton with a health route and table creation.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import APP_NAME, DEBUG
from app.db import create_tables, engine
from app.schemas import HealthResponse


# ── Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


# ── App setup ────────────────────────────────────────────────────────

app = FastAPI(
    title=APP_NAME,
    debug=DEBUG,
    docs_url="/docs" if DEBUG else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Static files and templates
_base = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=_base / "static"), name="static")
templates = Jinja2Templates(directory=str(_base / "templates"))


# ── Health route ─────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Quick check that the server is running and the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        db_status = "connected"
    except Exception:
        db_status = "unreachable"

    return HealthResponse(
        status="ok",
        app_name=APP_NAME,
        database=db_status,
    )
