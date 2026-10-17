"""
Authentication dependencies for FastAPI route protection.
"""

from fastapi import Depends, Request, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.auth.security import SESSION_COOKIE_NAME, decode_session_token


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    """
    Returns the currently logged-in User if the session cookie is valid,
    or None if the user is unauthenticated.
    """
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_cookie:
        return None

    user_id = decode_session_token(session_cookie)
    if user_id is None:
        return None

    user = db.get(User, user_id)
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    Enforces authentication on protected routes.
    If unauthenticated:
      - Redirects browser requests (Accept: text/html) to /auth/login with a 303 See Other.
      - Returns 401 Unauthorized for API/JSON requests.
    """
    user = get_current_user_optional(request, db)
    if user is not None:
        return user

    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header or "*/*" in accept_header:
        # Browser request: redirect to login
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Authentication required",
            headers={"Location": "/auth/login"},
        )

    # API / JSON request: return 401
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )
