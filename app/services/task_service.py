"""
Task service – Pure business logic for manual task management and history tracking.

Every function operates strictly in the scope of a specific user_id.
"""

from datetime import date, datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, distinct

from app.models import Task, TaskHistory


def is_task_overdue(task: Task, reference_date: date | None = None) -> bool:
    """
    Overdue is strictly derived: deadline before reference date (default today)
    and status not completed or cancelled. Never stored in the database.
    """
    if task.deadline is None:
        return False
    if task.status in ("completed", "cancelled"):
        return False
    ref = reference_date or date.today()
    return task.deadline < ref


def create_task(
    db: Session,
    user_id: int,
    title: str,
    description: str | None = None,
    subject: str | None = None,
    kind: str | None = None,
    deadline: date | None = None,
    estimated_hours: float | None = None,
    source: str = "manual",
    candidate_id: int | None = None,
) -> Task:
    """Creates a new task and writes an initial 'created' event in task_history."""
    task = Task(
        user_id=user_id,
        candidate_id=candidate_id,
        source=source,
        title=title.strip(),
        description=description.strip() if description else None,
        subject=subject.strip() if subject else None,
        kind=kind.strip().lower() if kind else "assignment",
        deadline=deadline,
        estimated_hours=estimated_hours,
        status="pending",
    )
    db.add(task)
    db.flush()

    history = TaskHistory(
        task_id=task.id,
        user_id=user_id,
        event="created",
        old_value=None,
        new_value=f"Task '{task.title}' created (source: {source})",
    )
    db.add(history)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, user_id: int, task_id: int) -> Task | None:
    """
    Retrieves a single task strictly filtered by user_id.
    Returns None if the task does not exist or belongs to another user.
    """
    stmt = select(Task).where(Task.id == task_id, Task.user_id == user_id)
    return db.scalar(stmt)


def list_tasks(
    db: Session,
    user_id: int,
    status_filter: str | None = None,
    subject_filter: str | None = None,
    reference_date: date | None = None,
) -> list[Task]:
    """
    Retrieves tasks for a user with optional filtering:
    - 'open': pending or in_progress
    - 'completed': completed
    - 'cancelled': cancelled
    - 'overdue': derived (deadline < today, status not completed or cancelled)
    - subject_filter: exact match on subject
    """
    ref_date = reference_date or date.today()
    stmt = select(Task).where(Task.user_id == user_id)

    if subject_filter and subject_filter.strip():
        stmt = stmt.where(Task.subject == subject_filter.strip())

    if status_filter == "open":
        stmt = stmt.where(Task.status.in_(["pending", "in_progress"]))
    elif status_filter == "completed":
        stmt = stmt.where(Task.status == "completed")
    elif status_filter == "cancelled":
        stmt = stmt.where(Task.status == "cancelled")
    elif status_filter == "overdue":
        stmt = stmt.where(
            Task.deadline.is_not(None),
            Task.deadline < ref_date,
            Task.status.not_in(["completed", "cancelled"]),
        )

    # Sort: earliest deadline first (NULLs last), then by id descending
    stmt = stmt.order_by(Task.deadline.asc().nulls_last(), Task.id.desc())
    return list(db.scalars(stmt).all())


def get_user_subjects(db: Session, user_id: int) -> list[str]:
    """Returns a sorted list of non-empty distinct subjects used by this user."""
    stmt = (
        select(Task.subject)
        .distinct()
        .where(Task.user_id == user_id, Task.subject.is_not(None), Task.subject != "")
        .order_by(Task.subject.asc())
    )
    return [s for s in db.scalars(stmt).all() if s]


def start_task(db: Session, user_id: int, task_id: int) -> Task | None:
    """Transitions a pending task to 'in_progress' and records history."""
    task = get_task(db, user_id, task_id)
    if not task:
        return None

    old_status = task.status
    task.status = "in_progress"

    history = TaskHistory(
        task_id=task.id,
        user_id=user_id,
        event="started",
        old_value=old_status,
        new_value="in_progress",
    )
    db.add(history)
    db.commit()
    db.refresh(task)
    return task


def complete_task(
    db: Session,
    user_id: int,
    task_id: int,
    actual_hours: float | None = None,
) -> Task | None:
    """Transitions task to 'completed', sets completed_at and optional actual_hours."""
    task = get_task(db, user_id, task_id)
    if not task:
        return None

    old_status = task.status
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    if actual_hours is not None:
        task.actual_hours = max(0.0, float(actual_hours))

    history = TaskHistory(
        task_id=task.id,
        user_id=user_id,
        event="completed",
        old_value=f"status={old_status}",
        new_value=f"status=completed, actual_hours={task.actual_hours}",
    )
    db.add(history)
    db.commit()
    db.refresh(task)
    return task


def cancel_task(db: Session, user_id: int, task_id: int) -> Task | None:
    """Transitions task to 'cancelled' and records history."""
    task = get_task(db, user_id, task_id)
    if not task:
        return None

    old_status = task.status
    task.status = "cancelled"

    history = TaskHistory(
        task_id=task.id,
        user_id=user_id,
        event="cancelled",
        old_value=old_status,
        new_value="cancelled",
    )
    db.add(history)
    db.commit()
    db.refresh(task)
    return task


def update_task(
    db: Session,
    user_id: int,
    task_id: int,
    title: str,
    description: str | None = None,
    subject: str | None = None,
    kind: str | None = None,
    deadline: date | None = None,
    estimated_hours: float | None = None,
) -> Task | None:
    """Updates task fields and writes history records for changes."""
    task = get_task(db, user_id, task_id)
    if not task:
        return None

    # Track deadline change separately if modified
    old_deadline = task.deadline
    if old_deadline != deadline:
        history_deadline = TaskHistory(
            task_id=task.id,
            user_id=user_id,
            event="deadline_changed",
            old_value=str(old_deadline) if old_deadline else "None",
            new_value=str(deadline) if deadline else "None",
        )
        db.add(history_deadline)

    task.title = title.strip()
    task.description = description.strip() if description else None
    task.subject = subject.strip() if subject else None
    task.kind = kind.strip().lower() if kind else task.kind
    task.deadline = deadline
    task.estimated_hours = estimated_hours

    history_update = TaskHistory(
        task_id=task.id,
        user_id=user_id,
        event="updated",
        old_value=None,
        new_value=f"Updated details for '{task.title}'",
    )
    db.add(history_update)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, user_id: int, task_id: int) -> bool:
    """Deletes task and associated history rows (via cascade). Returns True on success."""
    task = get_task(db, user_id, task_id)
    if not task:
        return False

    db.delete(task)
    db.commit()
    return True
