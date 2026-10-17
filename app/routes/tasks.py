"""
Tasks routes – HTTP handlers for manual task management and lifecycle actions.
Routes only parse requests, call services, and render templates.
"""

from datetime import date
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.config import APP_NAME
from app.db import get_db
from app.models import User
from app.auth.deps import get_current_user
from app.auth.security import generate_csrf_token, verify_csrf_token
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def parse_date(date_str: str | None) -> date | None:
    """Safely parse an ISO date string (YYYY-MM-DD). Returns None on error or empty."""
    if not date_str or not date_str.strip():
        return None
    try:
        return date.fromisoformat(date_str.strip())
    except ValueError:
        return None


def parse_float(val_str: str | None) -> float | None:
    """Safely parse a positive float. Returns None on error or empty."""
    if not val_str or not val_str.strip():
        return None
    try:
        val = float(val_str.strip())
        return max(0.0, val)
    except ValueError:
        return None


# ── Task List & Filter ───────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def list_tasks_page(
    request: Request,
    status: str | None = None,
    subject: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Renders the task list with backend-filtered tasks and manual add form.
    Filters:
      - status: 'open', 'completed', 'overdue', 'cancelled', 'all'
      - subject: string
    """
    cleaned_status = status.strip().lower() if status else "all"
    cleaned_subject = subject.strip() if subject else None

    tasks = task_service.list_tasks(
        db=db,
        user_id=current_user.id,
        status_filter=cleaned_status,
        subject_filter=cleaned_subject,
    )

    # Attach derived is_overdue property for template rendering
    for t in tasks:
        t.is_overdue = task_service.is_task_overdue(t)

    user_subjects = task_service.get_user_subjects(db, current_user.id)
    csrf_token = generate_csrf_token()

    return templates.TemplateResponse(
        request=request,
        name="tasks/index.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "tasks",
            "csrf_token": csrf_token,
            "tasks": tasks,
            "user_subjects": user_subjects,
            "current_status": cleaned_status,
            "current_subject": cleaned_subject,
            "form_data": {},
            "error": None,
        },
    )


# ── Create Task ──────────────────────────────────────────────────────

@router.post("")
@router.post("/")
def create_task_endpoint(
    request: Request,
    title: str = Form(""),
    subject: str = Form(""),
    kind: str = Form("assignment"),
    deadline: str = Form(""),
    estimated_hours: str = Form(""),
    description: str = Form(""),
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Creates a task manually with input validation and CSRF verification."""
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    cleaned_title = title.strip()
    if not cleaned_title:
        # Re-render with error
        tasks = task_service.list_tasks(db, current_user.id, status_filter="all")
        for t in tasks:
            t.is_overdue = task_service.is_task_overdue(t)
        user_subjects = task_service.get_user_subjects(db, current_user.id)
        new_csrf = generate_csrf_token()

        return templates.TemplateResponse(
            request=request,
            name="tasks/index.html",
            context={
                "app_name": APP_NAME,
                "current_user": current_user,
                "active_page": "tasks",
                "csrf_token": new_csrf,
                "tasks": tasks,
                "user_subjects": user_subjects,
                "current_status": "all",
                "current_subject": None,
                "form_data": {
                    "title": title,
                    "subject": subject,
                    "kind": kind,
                    "deadline": deadline,
                    "estimated_hours": estimated_hours,
                    "description": description,
                },
                "error": "Task title is required.",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    parsed_deadline = parse_date(deadline)
    parsed_hours = parse_float(estimated_hours)

    task_service.create_task(
        db=db,
        user_id=current_user.id,
        title=cleaned_title,
        description=description.strip() if description else None,
        subject=subject.strip() if subject else None,
        kind=kind.strip() if kind else "assignment",
        deadline=parsed_deadline,
        estimated_hours=parsed_hours,
        source="manual",
    )

    return RedirectResponse(url="/tasks", status_code=status.HTTP_303_SEE_OTHER)


# ── Edit / Update Task ───────────────────────────────────────────────

@router.get("/{task_id}/edit", response_class=HTMLResponse)
def edit_task_page(
    task_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Renders edit task page. Returns 404 if not found or belongs to another user."""
    task = task_service.get_task(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    csrf_token = generate_csrf_token()
    return templates.TemplateResponse(
        request=request,
        name="tasks/edit.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "tasks",
            "csrf_token": csrf_token,
            "task": task,
            "error": None,
        },
    )


@router.post("/{task_id}/update")
def update_task_endpoint(
    task_id: int,
    request: Request,
    title: str = Form(""),
    subject: str = Form(""),
    kind: str = Form("assignment"),
    deadline: str = Form(""),
    estimated_hours: str = Form(""),
    description: str = Form(""),
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates a task. Returns 404 if task does not belong to logged-in user."""
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    cleaned_title = title.strip()
    if not cleaned_title:
        task = task_service.get_task(db, current_user.id, task_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        new_csrf = generate_csrf_token()
        return templates.TemplateResponse(
            request=request,
            name="tasks/edit.html",
            context={
                "app_name": APP_NAME,
                "current_user": current_user,
                "active_page": "tasks",
                "csrf_token": new_csrf,
                "task": task,
                "error": "Task title cannot be empty.",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    updated = task_service.update_task(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
        title=cleaned_title,
        description=description.strip() if description else None,
        subject=subject.strip() if subject else None,
        kind=kind,
        deadline=parse_date(deadline),
        estimated_hours=parse_float(estimated_hours),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return RedirectResponse(url="/tasks", status_code=status.HTTP_303_SEE_OTHER)


# ── Task Lifecycle Actions (Start, Complete, Cancel) ─────────────────

@router.post("/{task_id}/start")
def start_task_endpoint(
    task_id: int,
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    task = task_service.start_task(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return RedirectResponse(url="/tasks", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{task_id}/complete")
def complete_task_endpoint(
    task_id: int,
    actual_hours: str = Form(""),
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    parsed_actual = parse_float(actual_hours)
    task = task_service.complete_task(db, current_user.id, task_id, actual_hours=parsed_actual)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return RedirectResponse(url="/tasks", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{task_id}/cancel")
def cancel_task_endpoint(
    task_id: int,
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    task = task_service.cancel_task(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return RedirectResponse(url="/tasks", status_code=status.HTTP_303_SEE_OTHER)


# ── Delete Task (with confirmation step) ─────────────────────────────

@router.get("/{task_id}/delete", response_class=HTMLResponse)
def delete_task_confirmation_page(
    task_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Presents a confirmation page before deleting the task."""
    task = task_service.get_task(db, current_user.id, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    csrf_token = generate_csrf_token()
    return templates.TemplateResponse(
        request=request,
        name="tasks/delete.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "tasks",
            "csrf_token": csrf_token,
            "task": task,
        },
    )


@router.post("/{task_id}/delete")
def delete_task_endpoint(
    task_id: int,
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    success = task_service.delete_task(db, current_user.id, task_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return RedirectResponse(url="/tasks", status_code=status.HTTP_303_SEE_OTHER)
