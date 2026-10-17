"""
Phase 3 tests – Manual Task CRUD, History Tracking, Derived Overdue,
Backend Filtering, and Strict User Isolation (404 on cross-user access).
"""

from datetime import date, timedelta
import pytest
from app.auth.security import generate_csrf_token
from app.models import Task, TaskHistory
from app.services import task_service


# ── Task CRUD & History Tests ────────────────────────────────────────

def test_manual_task_creation(client_a, user_a, db_session):
    csrf = generate_csrf_token()
    due = (date.today() + timedelta(days=5)).isoformat()

    resp = client_a.post(
        "/tasks",
        data={
            "title": "Data Structures Assignment 1",
            "subject": "CS201",
            "kind": "assignment",
            "deadline": due,
            "estimated_hours": "4.5",
            "description": "Implement AVL tree with rebalancing.",
            "csrf_token": csrf,
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/tasks"

    # Verify task in DB
    task = (
        db_session.query(Task)
        .filter(Task.user_id == user_a.id, Task.title == "Data Structures Assignment 1")
        .first()
    )
    assert task is not None
    assert task.subject == "CS201"
    assert task.kind == "assignment"
    assert task.estimated_hours == 4.5
    assert task.status == "pending"
    assert task.source == "manual"
    assert task.deadline == date.fromisoformat(due)

    # Verify history row created
    history = (
        db_session.query(TaskHistory)
        .filter(TaskHistory.task_id == task.id, TaskHistory.event == "created")
        .first()
    )
    assert history is not None
    assert history.user_id == user_a.id


def test_task_creation_validation_missing_title(client_a):
    csrf = generate_csrf_token()
    resp = client_a.post(
        "/tasks",
        data={
            "title": "   ",  # empty title
            "csrf_token": csrf,
        },
    )
    assert resp.status_code == 422
    assert "Task title is required" in resp.text


def test_task_start_lifecycle(client_a, user_a, db_session):
    task = task_service.create_task(db_session, user_a.id, title="Algorithm Problem Set")
    assert task.status == "pending"

    csrf = generate_csrf_token()
    resp = client_a.post(f"/tasks/{task.id}/start", data={"csrf_token": csrf})
    assert resp.status_code == 303

    db_session.refresh(task)
    assert task.status == "in_progress"

    # Verify history event
    history = (
        db_session.query(TaskHistory)
        .filter(TaskHistory.task_id == task.id, TaskHistory.event == "started")
        .first()
    )
    assert history is not None
    assert history.new_value == "in_progress"


def test_task_complete_lifecycle(client_a, user_a, db_session):
    task = task_service.create_task(
        db_session, user_a.id, title="DBMS Lab Report", estimated_hours=3.0
    )

    csrf = generate_csrf_token()
    resp = client_a.post(
        f"/tasks/{task.id}/complete",
        data={"csrf_token": csrf, "actual_hours": "3.5"},
    )
    assert resp.status_code == 303

    db_session.refresh(task)
    assert task.status == "completed"
    assert task.completed_at is not None
    assert task.actual_hours == 3.5

    # Verify history event
    history = (
        db_session.query(TaskHistory)
        .filter(TaskHistory.task_id == task.id, TaskHistory.event == "completed")
        .first()
    )
    assert history is not None
    assert "actual_hours=3.5" in history.new_value


def test_task_cancel_lifecycle(client_a, user_a, db_session):
    task = task_service.create_task(db_session, user_a.id, title="Optional Quiz Prep")

    csrf = generate_csrf_token()
    resp = client_a.post(f"/tasks/{task.id}/cancel", data={"csrf_token": csrf})
    assert resp.status_code == 303

    db_session.refresh(task)
    assert task.status == "cancelled"

    history = (
        db_session.query(TaskHistory)
        .filter(TaskHistory.task_id == task.id, TaskHistory.event == "cancelled")
        .first()
    )
    assert history is not None


def test_task_edit_and_deadline_change(client_a, user_a, db_session):
    initial_deadline = date.today() + timedelta(days=2)
    task = task_service.create_task(
        db_session, user_a.id, title="Physics Lab", deadline=initial_deadline
    )

    # View edit form
    edit_page = client_a.get(f"/tasks/{task.id}/edit")
    assert edit_page.status_code == 200
    assert "Physics Lab" in edit_page.text

    # Submit update with altered deadline
    new_deadline = date.today() + timedelta(days=5)
    csrf = generate_csrf_token()
    resp = client_a.post(
        f"/tasks/{task.id}/update",
        data={
            "title": "Physics Lab Record (Updated)",
            "subject": "Physics",
            "kind": "submission",
            "deadline": new_deadline.isoformat(),
            "estimated_hours": "2.0",
            "description": "Includes error propagation calculations.",
            "csrf_token": csrf,
        },
    )
    assert resp.status_code == 303

    db_session.refresh(task)
    assert task.title == "Physics Lab Record (Updated)"
    assert task.deadline == new_deadline
    assert task.subject == "Physics"
    assert task.estimated_hours == 2.0

    # Verify deadline_changed history event was recorded
    history_dl = (
        db_session.query(TaskHistory)
        .filter(TaskHistory.task_id == task.id, TaskHistory.event == "deadline_changed")
        .first()
    )
    assert history_dl is not None
    assert history_dl.old_value == str(initial_deadline)
    assert history_dl.new_value == str(new_deadline)


def test_task_delete_with_confirmation_step(client_a, user_a, db_session):
    task = task_service.create_task(db_session, user_a.id, title="Task To Delete")

    # GET confirmation page
    confirm_page = client_a.get(f"/tasks/{task.id}/delete")
    assert confirm_page.status_code == 200
    assert "Confirm Deletion" in confirm_page.text
    assert "Task To Delete" in confirm_page.text

    # POST confirm deletion
    csrf = generate_csrf_token()
    resp = client_a.post(f"/tasks/{task.id}/delete", data={"csrf_token": csrf})
    assert resp.status_code == 303

    # Ensure removed from DB
    assert db_session.query(Task).filter(Task.id == task.id).first() is None
    # Ensure cascade deleted history
    assert db_session.query(TaskHistory).filter(TaskHistory.task_id == task.id).first() is None


# ── Derived Overdue & Backend Filtering Tests ────────────────────────

def test_derived_overdue_not_stored(client_a, user_a, db_session):
    """
    Overdue is derived (deadline < today and status not in (completed, cancelled)).
    Never stored as a database column.
    """
    past_due = date.today() - timedelta(days=2)
    future_due = date.today() + timedelta(days=3)

    overdue_task = task_service.create_task(
        db_session, user_a.id, title="Overdue Assignment", deadline=past_due
    )
    future_task = task_service.create_task(
        db_session, user_a.id, title="Future Assignment", deadline=future_due
    )
    completed_past_task = task_service.create_task(
        db_session, user_a.id, title="Completed Past Assignment", deadline=past_due
    )
    task_service.complete_task(db_session, user_a.id, completed_past_task.id)

    # Derived function check
    assert task_service.is_task_overdue(overdue_task) is True
    assert task_service.is_task_overdue(future_task) is False
    assert task_service.is_task_overdue(completed_past_task) is False

    # Check filter: ?status=overdue
    resp = client_a.get("/tasks?status=overdue")
    assert resp.status_code == 200
    assert "Overdue Assignment" in resp.text
    assert "Future Assignment" not in resp.text
    assert "Completed Past Assignment" not in resp.text


def test_backend_status_and_subject_filters(client_a, user_a, db_session):
    task_service.create_task(db_session, user_a.id, title="Math Homework", subject="Maths")
    task_cs = task_service.create_task(
        db_session, user_a.id, title="CS Assignment", subject="Computer Science"
    )
    task_service.complete_task(db_session, user_a.id, task_cs.id)

    # Filter by subject
    resp_math = client_a.get("/tasks?subject=Maths")
    assert resp_math.status_code == 200
    assert "Math Homework" in resp_math.text
    assert "CS Assignment" not in resp_math.text

    # Filter by status=completed
    resp_comp = client_a.get("/tasks?status=completed")
    assert resp_comp.status_code == 200
    assert "CS Assignment" in resp_comp.text
    assert "Math Homework" not in resp_comp.text

    # Filter by status=open
    resp_open = client_a.get("/tasks?status=open")
    assert resp_open.status_code == 200
    assert "Math Homework" in resp_open.text
    assert "CS Assignment" not in resp_open.text


# ── Strict User Isolation Tests (B cannot access A, returns 404) ──────

def test_user_isolation_user_b_cannot_view_or_modify_user_a_tasks(
    client_a, client_b, user_a, user_b, db_session
):
    """
    Spec Section 4 & Phase 3 rule:
    'A user must never be able to read or change another user's rows
     (return 404, not 403, for other users' records).
     Write real isolation tests using client_a and client_b:
     B cannot view, edit, complete or delete A's tasks.'
    """
    # User A creates a task
    task_a = task_service.create_task(
        db_session,
        user_id=user_a.id,
        title="Secret Thesis Research",
        subject="AI",
        deadline=date.today() + timedelta(days=10),
        estimated_hours=8.0,
    )

    # 1. User B viewing /tasks must NOT see User A's task
    resp_b_list = client_b.get("/tasks")
    assert resp_b_list.status_code == 200
    assert "Secret Thesis Research" not in resp_b_list.text

    # 2. User B trying to view edit page of User A's task -> 404
    resp_b_edit = client_b.get(f"/tasks/{task_a.id}/edit")
    assert resp_b_edit.status_code == 404

    # 3. User B trying to update User A's task -> 404
    csrf_b = generate_csrf_token()
    resp_b_update = client_b.post(
        f"/tasks/{task_a.id}/update",
        data={
            "title": "Hacked Title",
            "csrf_token": csrf_b,
        },
    )
    assert resp_b_update.status_code == 404

    # 4. User B trying to start User A's task -> 404
    resp_b_start = client_b.post(f"/tasks/{task_a.id}/start", data={"csrf_token": csrf_b})
    assert resp_b_start.status_code == 404

    # 5. User B trying to complete User A's task -> 404
    resp_b_complete = client_b.post(
        f"/tasks/{task_a.id}/complete",
        data={"csrf_token": csrf_b, "actual_hours": "1.0"},
    )
    assert resp_b_complete.status_code == 404

    # 6. User B trying to cancel User A's task -> 404
    resp_b_cancel = client_b.post(f"/tasks/{task_a.id}/cancel", data={"csrf_token": csrf_b})
    assert resp_b_cancel.status_code == 404

    # 7. User B trying to view delete confirmation of User A's task -> 404
    resp_b_delete_page = client_b.get(f"/tasks/{task_a.id}/delete")
    assert resp_b_delete_page.status_code == 404

    # 8. User B trying to delete User A's task -> 404
    resp_b_delete = client_b.post(f"/tasks/{task_a.id}/delete", data={"csrf_token": csrf_b})
    assert resp_b_delete.status_code == 404

    # 9. Verify User A's task is completely unmodified in database
    db_session.refresh(task_a)
    assert task_a.title == "Secret Thesis Research"
    assert task_a.status == "pending"
    assert task_a.user_id == user_a.id
