"""
Phase 2 tests – Authentication, session management, CSRF protection,
and user isolation setup.
"""

import pytest
from app.auth.security import generate_csrf_token, SESSION_COOKIE_NAME, decode_session_token
from app.models import User, UserSettings


# ── Signup Tests ─────────────────────────────────────────────────────

def test_signup_success(client, db_session):
    csrf = generate_csrf_token()
    resp = client.post(
        "/auth/signup",
        data={
            "display_name": "Rohan Sharma",
            "email": "rohan@college.edu",
            "password": "StrongPassword123",
            "csrf_token": csrf,
        },
    )

    # Should redirect (303) to /dashboard
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"

    # Should set HttpOnly, SameSite=Lax session cookie
    cookie = resp.cookies.get(SESSION_COOKIE_NAME)
    assert cookie is not None

    # Check user and default settings exist in DB
    user = db_session.query(User).filter(User.email == "rohan@college.edu").first()
    assert user is not None
    assert user.display_name == "Rohan Sharma"
    assert user.password_hash != "StrongPassword123"  # must be hashed

    # Decoded session token must match user id
    assert decode_session_token(cookie) == user.id

    # User settings must be initialized with spec defaults
    settings = db_session.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    assert settings is not None
    assert settings.free_hours_per_day == 3.0
    assert settings.free_days == "Mon,Tue,Wed,Thu,Fri,Sat,Sun"
    assert settings.overrun_min_samples == 5


def test_signup_duplicate_email(client, db_session):
    # First signup
    csrf1 = generate_csrf_token()
    client.post(
        "/auth/signup",
        data={
            "display_name": "First User",
            "email": "duplicate@college.edu",
            "password": "Password123",
            "csrf_token": csrf1,
        },
    )

    # Attempt second signup with same email
    csrf2 = generate_csrf_token()
    resp = client.post(
        "/auth/signup",
        data={
            "display_name": "Second User",
            "email": "duplicate@college.edu",
            "password": "Password456",
            "csrf_token": csrf2,
        },
    )

    assert resp.status_code == 422
    assert "already exists" in resp.text
    # Should retain input name and email
    assert "duplicate@college.edu" in resp.text
    assert "Second User" in resp.text


def test_signup_short_password(client):
    csrf = generate_csrf_token()
    resp = client.post(
        "/auth/signup",
        data={
            "display_name": "Short Pass User",
            "email": "short@college.edu",
            "password": "short",
            "csrf_token": csrf,
        },
    )
    assert resp.status_code == 422
    assert "at least 8 characters" in resp.text


# ── Login Tests ──────────────────────────────────────────────────────

def test_login_success(client, db_session):
    # Create user directly or via signup
    csrf_signup = generate_csrf_token()
    client.post(
        "/auth/signup",
        data={
            "display_name": "Login Tester",
            "email": "login_tester@college.edu",
            "password": "CorrectPassword123",
            "csrf_token": csrf_signup,
        },
    )

    # Now attempt login
    csrf_login = generate_csrf_token()
    resp = client.post(
        "/auth/login",
        data={
            "email": "login_tester@college.edu",
            "password": "CorrectPassword123",
            "csrf_token": csrf_login,
        },
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    cookie = resp.cookies.get(SESSION_COOKIE_NAME)
    assert cookie is not None


def test_login_wrong_password(client):
    # Ensure user exists
    csrf_signup = generate_csrf_token()
    client.post(
        "/auth/signup",
        data={
            "display_name": "Wrong Pass User",
            "email": "wrongpass@college.edu",
            "password": "CorrectPassword123",
            "csrf_token": csrf_signup,
        },
    )

    # Login with wrong password
    csrf_login = generate_csrf_token()
    resp = client.post(
        "/auth/login",
        data={
            "email": "wrongpass@college.edu",
            "password": "WrongPassword999",
            "csrf_token": csrf_login,
        },
    )

    assert resp.status_code == 401
    assert "Invalid email or password" in resp.text


def test_login_nonexistent_email(client):
    csrf_login = generate_csrf_token()
    resp = client.post(
        "/auth/login",
        data={
            "email": "does_not_exist@college.edu",
            "password": "SomePassword123",
            "csrf_token": csrf_login,
        },
    )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.text


# ── Logout Tests ─────────────────────────────────────────────────────

def test_logout(client):
    # Log in first
    csrf_signup = generate_csrf_token()
    signup_resp = client.post(
        "/auth/signup",
        data={
            "display_name": "Logout User",
            "email": "logout_test@college.edu",
            "password": "Password123",
            "csrf_token": csrf_signup,
        },
    )
    # Verify dashboard is accessible while logged in
    dash_resp = client.get("/dashboard")
    assert dash_resp.status_code == 200

    # Perform logout
    csrf_logout = generate_csrf_token()
    logout_resp = client.post(
        "/auth/logout",
        data={"csrf_token": csrf_logout},
    )
    assert logout_resp.status_code == 303
    assert logout_resp.headers["location"] == "/auth/login"

    # Verify dashboard is no longer accessible
    after_resp = client.get("/dashboard", headers={"accept": "text/html"})
    assert after_resp.status_code == 303
    assert after_resp.headers["location"] == "/auth/login"


# ── Route Protection & Redirection ───────────────────────────────────

def test_protected_route_redirects_unauthenticated_browser(client):
    # Browser request without session cookie
    resp = client.get("/dashboard", headers={"accept": "text/html"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


def test_protected_route_returns_401_for_api(client):
    # API client without session cookie
    resp = client.get("/dashboard", headers={"accept": "application/json"})
    assert resp.status_code == 401


# ── CSRF Protection ──────────────────────────────────────────────────

def test_signup_rejected_with_invalid_csrf(client):
    resp = client.post(
        "/auth/signup",
        data={
            "display_name": "Attacker",
            "email": "attacker@evil.com",
            "password": "Password123",
            "csrf_token": "tampered-or-invalid-token",
        },
    )
    assert resp.status_code == 422
    assert "Security token was invalid or expired" in resp.text


# ── User Isolation Setup Verification ────────────────────────────────

def test_user_isolation_clients(client_a, client_b, user_a, user_b):
    """
    Verifies that client_a and client_b authenticate as distinct users.
    This fixture setup is reused in Phase 3 for data isolation tests.
    """
    resp_a = client_a.get("/dashboard")
    assert resp_a.status_code == 200
    assert user_a.display_name in resp_a.text
    assert user_b.display_name not in resp_a.text

    resp_b = client_b.get("/dashboard")
    assert resp_b.status_code == 200
    assert user_b.display_name in resp_b.text
    assert user_a.display_name not in resp_b.text
