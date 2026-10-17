"""
Study Rescue – FastAPI application entry point.

Phase 2: Authentication, session management, and route protection.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import APP_NAME, DEBUG
from app.db import create_tables, engine
from app.schemas import HealthResponse
from app.models import User
from app.auth.deps import get_current_user, get_current_user_optional
from app.auth.security import generate_csrf_token
from app.routes.auth import router as auth_router


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

# Routers
app.include_router(auth_router)


# ── Root / Landing placeholder ───────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def get_root(request: Request, current_user: User | None = Depends(get_current_user_optional)):
    """Landing route – redirects to dashboard if authenticated, or login."""
    if current_user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/dashboard", status_code=303)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/auth/login", status_code=303)


# ── Protected Dashboard Route (Phase 2 placeholder) ──────────────────

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(request: Request, current_user: User = Depends(get_current_user)):
    """
    Protected dashboard endpoint.
    Used in Phase 2 to verify route protection and session isolation.
    """
    csrf_token = generate_csrf_token()
    return HTMLResponse(
        content=f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <title>Dashboard – {APP_NAME}</title>
          <link rel="stylesheet" href="/static/css/style.css">
        </head>
        <body>
          <div class="container" style="padding-top: 2rem;">
            <h1>Dashboard</h1>
            <p>Welcome, <strong id="user-display-name">{current_user.display_name}</strong> ({current_user.email})</p>
            <div style="margin-top: 1.5rem;">
              <form method="post" action="/auth/logout">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <button type="submit" class="btn btn-primary" id="logout-btn">Log out</button>
              </form>
            </div>
          </div>
        </body>
        </html>
        """
    )


# ── Health route ─────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Quick check that the server is running and the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "unreachable"

    return HealthResponse(
        status="ok",
        app_name=APP_NAME,
        database=db_status,
    )
