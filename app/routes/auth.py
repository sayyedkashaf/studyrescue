"""
Authentication routes:
- GET /auth/signup, POST /auth/signup
- GET /auth/login, POST /auth/login
- POST /auth/logout
"""

import re
from fastapi import APIRouter, Depends, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from pathlib import Path

from app.config import APP_NAME
from app.db import get_db
from app.models import User, UserSettings
from app.auth.security import (
    hash_password,
    verify_password,
    create_session_token,
    generate_csrf_token,
    verify_csrf_token,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
)
from app.auth.deps import get_current_user_optional

router = APIRouter(prefix="/auth", tags=["auth"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Signup ───────────────────────────────────────────────────────────

@router.get("/signup", response_class=HTMLResponse)
def get_signup_page(request: Request, db: Session = Depends(get_db)):
    # If already logged in, redirect to dashboard
    current_user = get_current_user_optional(request, db)
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    csrf_token = generate_csrf_token()
    return templates.TemplateResponse(
        request=request,
        name="auth/signup.html",
        context={
            "app_name": APP_NAME,
            "csrf_token": csrf_token,
            "errors": {},
            "form_data": {},
        },
    )


@router.post("/signup")
def post_signup(
    request: Request,
    response: Response,
    display_name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    errors: dict[str, str] = {}
    cleaned_name = display_name.strip()
    cleaned_email = email.strip().lower()

    # CSRF check
    if not verify_csrf_token(csrf_token):
        errors["general"] = "Security token was invalid or expired. Please try again."

    # Input validation
    if not cleaned_name:
        errors["display_name"] = "Please enter your name."
    elif len(cleaned_name) > 100:
        errors["display_name"] = "Name must be 100 characters or fewer."

    if not cleaned_email:
        errors["email"] = "Please enter your email address."
    elif not EMAIL_REGEX.match(cleaned_email):
        errors["email"] = "Please enter a valid email address."
    else:
        # Check uniqueness
        existing_user = db.scalar(select(User).where(User.email == cleaned_email))
        if existing_user:
            errors["email"] = "An account with this email address already exists."

    if not password:
        errors["password"] = "Please enter a password."
    elif len(password) < 8:
        errors["password"] = "Password must be at least 8 characters long."

    if errors:
        # Re-render with inline errors and a fresh CSRF token
        new_csrf = generate_csrf_token()
        return templates.TemplateResponse(
            request=request,
            name="auth/signup.html",
            context={
                "app_name": APP_NAME,
                "csrf_token": new_csrf,
                "errors": errors,
                "form_data": {
                    "display_name": display_name,
                    "email": email,
                },
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Create user and default settings
    user = User(
        email=cleaned_email,
        password_hash=hash_password(password),
        display_name=cleaned_name,
    )
    db.add(user)
    db.flush()  # populate user.id

    settings = UserSettings(
        user_id=user.id,
        free_hours_per_day=3.0,
        free_days="Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        overrun_min_samples=5,
    )
    db.add(settings)
    db.commit()
    db.refresh(user)

    # Issue session cookie and redirect
    session_token = create_session_token(user.id)
    redirect = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return redirect


# ── Login ────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
def get_login_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user_optional(request, db)
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    csrf_token = generate_csrf_token()
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "app_name": APP_NAME,
            "csrf_token": csrf_token,
            "errors": {},
            "form_data": {},
        },
    )


@router.post("/login")
def post_login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    errors: dict[str, str] = {}
    cleaned_email = email.strip().lower()

    if not verify_csrf_token(csrf_token):
        errors["general"] = "Security token was invalid or expired. Please try again."

    user = None
    if not cleaned_email:
        errors["email"] = "Please enter your email."
    if not password:
        errors["password"] = "Please enter your password."

    if not errors:
        user = db.scalar(select(User).where(User.email == cleaned_email))
        if not user or not verify_password(password, user.password_hash):
            errors["general"] = "Invalid email or password."

    if errors:
        new_csrf = generate_csrf_token()
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "app_name": APP_NAME,
                "csrf_token": new_csrf,
                "errors": errors,
                "form_data": {"email": email},
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # Success: set session cookie and redirect to dashboard
    session_token = create_session_token(user.id)
    redirect = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return redirect


# ── Logout ───────────────────────────────────────────────────────────

@router.post("/logout")
def post_logout(
    csrf_token: str = Form(""),
):
    # Verify CSRF to prevent unauthorized logout via image tags/cross-origin posts
    if not verify_csrf_token(csrf_token):
        # Redirect anyway or fail safe
        pass

    redirect = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
    )
    return redirect
