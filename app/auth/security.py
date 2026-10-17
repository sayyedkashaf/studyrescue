"""
Authentication security utilities:
- Password hashing with bcrypt
- Signed session cookie tokens with itsdangerous
- Signed CSRF tokens with itsdangerous
"""

import time
import secrets
import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import SECRET_KEY

# Serializers for session cookies and CSRF tokens
_session_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="studyrescue-session")
_csrf_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="studyrescue-csrf")

SESSION_COOKIE_NAME = "studyrescue_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 days
CSRF_MAX_AGE_SECONDS = 60 * 60 * 2          # 2 hours


# ── Password Hashing ─────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    pw_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        pw_bytes = password.encode("utf-8")
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hash_bytes)
    except Exception:
        return False


# ── Session Tokens ───────────────────────────────────────────────────

def create_session_token(user_id: int) -> str:
    """Create a signed, tamper-proof session token containing user_id."""
    return _session_serializer.dumps({"user_id": user_id, "iat": int(time.time())})


def decode_session_token(token: str) -> int | None:
    """
    Decode and verify a signed session token.
    Returns user_id if valid, or None if invalid/expired.
    """
    try:
        data = _session_serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return data.get("user_id")
    except (BadSignature, SignatureExpired, Exception):
        return None


# ── CSRF Tokens ──────────────────────────────────────────────────────

def generate_csrf_token() -> str:
    """Generate a signed CSRF token with a timestamp and random entropy."""
    payload = {
        "t": int(time.time()),
        "r": secrets.token_hex(8),
    }
    return _csrf_serializer.dumps(payload)


def verify_csrf_token(token: str | None) -> bool:
    """
    Verify a signed CSRF token.
    Returns True if valid and not expired, False otherwise.
    """
    if not token:
        return False
    try:
        _csrf_serializer.loads(token, max_age=CSRF_MAX_AGE_SECONDS)
        return True
    except (BadSignature, SignatureExpired, Exception):
        return False
