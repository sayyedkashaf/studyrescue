"""
Study Rescue – FastAPI application entry point.

Phase 2: Authentication, session management, and route protection.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.config import APP_NAME, DEBUG, ENV, CORS_ENABLED, CORS_ALLOW_ORIGINS, CORS_ALLOW_CREDENTIALS, SESSION_COOKIE_SECURE, SESSION_COOKIE_SAMESITE, SESSION_COOKIE_DOMAIN, FRONTEND_URL
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
from app.routes.landing import router as landing_router


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

# ── CORS middleware (production cross-origin support) ────────────────

# Always enable CORS if explicitly set, or auto-enable in production
_enable_cors = CORS_ENABLED or (ENV == "production")
if _enable_cors:
    if CORS_ALLOW_ORIGINS:
        _allow_origins = CORS_ALLOW_ORIGINS
    elif FRONTEND_URL:
        _allow_origins = [FRONTEND_URL]
    else:
        _allow_origins = ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allow_origins,
        allow_credentials=CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Set-Cookie"],
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
app.include_router(landing_router)


# ── Root / Landing placeholder ───────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def get_root(request: Request, current_user: User | None = Depends(get_current_user_optional)):
    """Landing route – redirects to dashboard if authenticated, or login."""
    from fastapi.responses import RedirectResponse
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/auth/login", status_code=303)


# NOTE: The /dashboard route is handled by dashboard_router (routes/dashboard.py)
# which uses the proper base.html template with dark theme and sidebar.


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
