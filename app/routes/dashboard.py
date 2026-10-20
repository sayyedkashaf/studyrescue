from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import APP_NAME
from app.db import get_db
from app.models import User, UserSettings
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
    open_tasks = task_service.list_tasks(db, current_user.id, status_filter="open")
    completed_tasks = task_service.list_tasks(db, current_user.id, status_filter="completed")
    overdue_tasks = task_service.list_tasks(db, current_user.id, status_filter="overdue")
    today = date.today()
    due_soon = [t for t in open_tasks if t.deadline and today <= t.deadline <= today + timedelta(days=7)]

    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    free_hours = settings.free_hours_per_day if settings else 3.0
    free_days = settings.free_days if settings else "Mon,Tue,Wed,Thu,Fri,Sat,Sun"
    feasibility = check_feasibility(open_tasks, today, free_hours_per_day=free_hours, free_days=free_days)

    priority = {"infeasible": 0, "tight": 1, "feasible": 2}
    ranked = sorted(feasibility.tasks, key=lambda x: (priority.get(x["status"], 3), x["days_left"]))
    risk_list = []
    for item in ranked[:5]:
        risk_list.append({
            "title": getattr(item["task"], "title", None),
            "deadline": item["deadline"],
            "risk": "Risk: " + risk_level(status=item["status"], days_left=item["days_left"], overdue=item["deadline"] < today),
            "sentence": item["sentence"],
        })

    risk_message = "Add estimates to see deadline risk." if not feasibility.tasks else None

    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context={
            "app_name": APP_NAME,
            "user": current_user,
            "active_page": "dashboard",
            "open_count": len(open_tasks),
            "completed_count": len(completed_tasks),
            "overdue_count": len(overdue_tasks),
            "due_soon_count": len(due_soon),
            "risk_list": risk_list,
            "risk_message": risk_message,
        },
    )
