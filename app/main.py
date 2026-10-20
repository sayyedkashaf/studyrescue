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
from app.routes.tasks import router as tasks_router
from app.routes.imports import router as imports_router
from app.routes.review import router as review_router
from app.routes.evaluation import router as evaluation_router
from app.routes.settings import router as settings_router
from app.routes.dashboard import router as dashboard_router


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
app.include_router(tasks_router)
app.include_router(imports_router)
app.include_router(review_router)
app.include_router(evaluation_router)
app.include_router(settings_router)
app.include_router(dashboard_router)


# ── Root / Landing placeholder ───────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def get_root(request: Request, current_user: User | None = Depends(get_current_user_optional)):
    """Landing route – redirects to dashboard if authenticated, or login."""
    from fastapi.responses import RedirectResponse
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/auth/login", status_code=303)


# ── Protected Dashboard Route ────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(request: Request, current_user: User = Depends(get_current_user)):
    """
    Dashboard route – renders welcome card and quick navigation.
    Full analytics and metrics built in Phase 9.
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
          <div class="app-layout">
            <aside class="sidebar" aria-label="Main Navigation">
              <div class="sidebar-header">
                <a href="/dashboard" class="sidebar-brand">
                  {APP_NAME}
                  <span>University Workload</span>
                </a>
              </div>
              <ul class="sidebar-nav">
                <li><a href="/dashboard" class="active">Dashboard</a></li>
                <li><a href="/tasks">Tasks</a></li>
                <li><a href="/imports">Imports</a></li>
                <li><a href="/settings">Settings</a></li>
                <li><a href="/evaluation">Evaluation</a></li>
              </ul>
              <div class="sidebar-footer">
                <div class="user-info">
                  {current_user.display_name}
                  <span class="user-email">{current_user.email}</span>
                </div>
                <form method="post" action="/auth/logout">
                  <input type="hidden" name="csrf_token" value="{csrf_token}">
                  <button type="submit" id="logout-btn">Log out</button>
                </form>
              </div>
            </aside>
            <main class="main-content" id="main-content">
              <h1>Dashboard</h1>
              <p>Welcome back, <strong id="user-display-name">{current_user.display_name}</strong>.</p>
              <div class="card" style="margin-top: 1.5rem;">
                <h2 class="card-title">Quick Actions</h2>
                <p style="margin-bottom: 1rem;">View and manage your tasks, track deadlines, and log hours.</p>
                <a href="/tasks" class="btn btn-primary">Go to Tasks &rarr;</a>
              </div>
            </main>
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
