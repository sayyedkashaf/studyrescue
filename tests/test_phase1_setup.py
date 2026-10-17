"""
Phase 1 tests – project skeleton, config, database creation and health route.
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

# Point to a test database so we don't touch the real one
os.environ["DATABASE_URL"] = "sqlite:///data/test_studyrescue.db"

from app.main import app
from app.db import engine, create_tables, Base


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Ensure all tables are created before tests run."""
    create_tables()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


# ── Config ───────────────────────────────────────────────────────────

def test_config_loads():
    from app.config import APP_NAME, SECRET_KEY, DATABASE_URL
    assert APP_NAME  # non-empty
    assert SECRET_KEY  # non-empty
    assert "sqlite" in DATABASE_URL


# ── Tables exist ─────────────────────────────────────────────────────

EXPECTED_TABLES = [
    "users",
    "user_settings",
    "import_batches",
    "messages",
    "extraction_runs",
    "candidates",
    "tasks",
    "task_history",
]


def test_all_tables_created():
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    for table in EXPECTED_TABLES:
        assert table in table_names, f"Table '{table}' was not created"


def test_users_table_columns():
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("users")}
    assert {"id", "email", "password_hash", "display_name", "created_at"} <= cols


def test_tasks_table_columns():
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("tasks")}
    expected = {
        "id", "user_id", "candidate_id", "source", "title", "description",
        "subject", "kind", "deadline", "estimated_hours", "actual_hours",
        "status", "completed_at", "created_at",
    }
    assert expected <= cols


def test_candidates_table_columns():
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("candidates")}
    expected = {
        "id", "user_id", "message_id", "run_id", "kind", "title", "subject",
        "deadline_text", "deadline_date", "deadline_flag", "estimated_hours",
        "certainty", "quote", "status", "suppressed_reason", "created_at",
    }
    assert expected <= cols


# ── Health route ─────────────────────────────────────────────────────

def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_response_body(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert data["app_name"]  # non-empty
    assert data["database"] == "connected"


# ── Foreign Key & Cascade Enforcement ────────────────────────────────

def test_foreign_key_enforced_nonexistent_user():
    """Inserting a Task with a user_id that does not exist must raise an IntegrityError."""
    from sqlalchemy.exc import IntegrityError
    from app.models import Task
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        orphan_task = Task(
            user_id=999999,  # does not exist
            title="Orphan Task",
        )
        session.add(orphan_task)
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_cascade_delete_user_deletes_tasks():
    """Deleting a user must cascade delete their associated tasks."""
    from app.models import User, Task
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        user = User(
            email="fk_cascade_test@example.com",
            password_hash="hashedpass",
            display_name="Cascade Tester",
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        task = Task(
            user_id=user.id,
            title="Cascade Task",
        )
        session.add(task)
        session.commit()
        task_id = task.id

        assert session.get(Task, task_id) is not None

        # Delete user
        session.delete(user)
        session.commit()

        # Task must be gone
        assert session.get(Task, task_id) is None
    finally:
        session.close()

