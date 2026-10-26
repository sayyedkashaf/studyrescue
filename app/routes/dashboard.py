from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import APP_NAME
from app.db import get_db
from app.models import User, UserSettings, Task
from app.auth.deps import get_current_user
from app.services import task_service
from app.planning.feasibility import check_feasibility
from app.planning.risk import risk_level

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    all_tasks = db.query(Task).filter(Task.user_id == current_user.id).all()
    open_tasks = [t for t in all_tasks if t.status in ("pending", "in_progress")]
    completed_tasks = [t for t in all_tasks if t.status == "completed"]
    overdue_tasks = [t for t in all_tasks if t.status in ("pending", "in_progress") and t.deadline and t.deadline < date.today()]
    today = date.today()
    due_this_week = [t for t in open_tasks if t.deadline and today <= t.deadline <= today + timedelta(days=7)]

    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    free_hours = settings.free_hours_per_day if settings else 3.0
    free_days = settings.free_days if settings else "Mon,Tue,Wed,Thu,Fri,Sat,Sun"
    feasibility = check_feasibility(open_tasks, today, free_hours_per_day=free_hours, free_days=free_days)

    priority = {"infeasible": 0, "tight": 1, "feasible": 2}
    ranked = sorted(feasibility.tasks, key=lambda x: (priority.get(x["status"], 3), x["days_left"]))
    risk_list = []
    for item in ranked:
        risk_list.append({
            "title": getattr(item["task"], "title", None),
            "deadline": item["deadline"],
            "status": item["status"],
            "needed": item["needed"],
            "available": item["available"],
            "slack": item["slack"],
            "risk": "Risk: " + risk_level(status=item["status"], days_left=item["days_left"], overdue=(item["deadline"] < today)),
            "sentence": item["sentence"],
        })

    risk_message = "Add estimates to see deadline risk." if not feasibility.tasks else None
    what_to_do_next = None
    if open_tasks:
        with_deadline = [t for t in open_tasks if t.deadline]
        if with_deadline:
            what_to_do_next = sorted(with_deadline, key=lambda x: (x.deadline, x.id))[0]
        else:
            what_to_do_next = open_tasks[0]

    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "user": current_user,
            "active_page": "dashboard",
            "open_count": len(open_tasks),
            "completed_count": len(completed_tasks),
            "overdue_count": len(overdue_tasks),
            "due_this_week_count": len(due_this_week),
            "risk_list": risk_list,
            "risk_message": risk_message,
            "what_to_do_next": what_to_do_next,
            "has_tasks": len(all_tasks) > 0,
        },
    )
