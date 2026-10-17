"""
Shared pytest fixtures for Study Rescue test suite.
Provides a clean SQLite database, test client, and user isolation fixtures.
"""

import os
import pytest
from fastapi.testclient import TestClient

# Ensure test DB is set
TEST_DB_PATH = "data/test_studyrescue.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from app.db import Base, engine, SessionLocal, get_db, create_tables
from app.main import app
from app.models import User, UserSettings
from app.auth.security import hash_password, create_session_token, SESSION_COOKIE_NAME


def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def init_test_db():
    """Create all tables in the test database for the session and clean up after."""
    os.makedirs("data", exist_ok=True)
    create_tables()
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


@pytest.fixture()
def db_session():
    """Yields a database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    """Base test client without an active session."""
    return TestClient(app, follow_redirects=False)


# ── Helper to create a user ──────────────────────────────────────────

def create_user(
    db,
    email: str = "student@example.com",
    password: str = "StudyRescuePass123",
    display_name: str = "Test Student",
) -> User:
    """Helper to insert a user and default settings directly into DB."""
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return existing

    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    settings = UserSettings(
        user_id=user.id,
        free_hours_per_day=3.0,
        free_days="Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        overrun_min_samples=5,
    )
    db.add(settings)
    db.commit()
    return user


# ── User Isolation Test Setup (Reusable for Phase 3+) ────────────────

@pytest.fixture()
def user_a(db_session):
    return create_user(db_session, email="user_a@university.ac.in", display_name="Student A")


@pytest.fixture()
def user_b(db_session):
    return create_user(db_session, email="user_b@university.ac.in", display_name="Student B")


@pytest.fixture()
def client_a(user_a):
    """Test client authenticated as User A."""
    token = create_session_token(user_a.id)
    c = TestClient(app, follow_redirects=False)
    c.cookies.set(SESSION_COOKIE_NAME, token)
    return c


@pytest.fixture()
def client_b(user_b):
    """Test client authenticated as User B."""
    token = create_session_token(user_b.id)
    c = TestClient(app, follow_redirects=False)
    c.cookies.set(SESSION_COOKIE_NAME, token)
    return c
