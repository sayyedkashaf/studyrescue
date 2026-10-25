from pathlib import Path

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import APP_NAME
from app.db import get_db
from app.models import User, UserSettings, ImportBatch, Message, ExtractionRun, Candidate, Task, TaskHistory
from app.auth.deps import get_current_user
from app.auth.security import generate_csrf_token, verify_csrf_token

router = APIRouter(prefix="/settings", tags=["settings"])

router = APIRouter(prefix="/settings", tags=["settings"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def settings_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    free_hours = settings.free_hours_per_day if settings else None
    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "settings",
            "display_name": current_user.display_name,
            "free_hours_per_day": free_hours,
            "csrf_token": generate_csrf_token(),
            "error": None,
        },
    )


@router.post("", response_class=HTMLResponse)
@router.post("/", response_class=HTMLResponse)
def settings_update(
    request: Request,
    display_name: str = Form(""),
    free_hours_per_day: str = Form(""),
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    cleaned_name = display_name.strip()
    error = None
    try:
        hours = float(free_hours_per_day.strip())
    except (ValueError, AttributeError):
        hours = None
    if not (1 <= len(cleaned_name) <= 60):
        error = "Display name must be 1 to 60 characters."
    elif hours is None or hours < 0 or hours > 24:
        error = "Free hours per day must be a number from 0 to 24."

    if error:
        new_csrf = generate_csrf_token()
        return templates.TemplateResponse(
            request=request,
            name="settings/index.html",
            context={
                "app_name": APP_NAME,
                "current_user": current_user,
                "active_page": "settings",
                "display_name": cleaned_name,
                "free_hours_per_day": free_hours_per_day,
                "error": error,
                "csrf_token": new_csrf,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    current_user.display_name = cleaned_name
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
    settings.free_hours_per_day = hours
    db.commit()
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/delete-data", response_class=HTMLResponse)
def delete_data_page(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="settings/delete_data.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "settings",
            "csrf_token": generate_csrf_token(),
        },
    )


@router.post("/delete-data", response_class=HTMLResponse)
def delete_data(request: Request, csrf_token: str = Form(""), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")
    uid = current_user.id
    try:
        db.query(TaskHistory).filter(TaskHistory.user_id == uid).delete(synchronize_session=False)
        db.query(Task).filter(Task.user_id == uid).delete(synchronize_session=False)
        db.query(Candidate).filter(Candidate.user_id == uid).delete(synchronize_session=False)
        db.query(ExtractionRun).filter(ExtractionRun.user_id == uid).delete(synchronize_session=False)
        db.query(Message).filter(Message.user_id == uid).delete(synchronize_session=False)
        db.query(ImportBatch).filter(ImportBatch.user_id == uid).delete(synchronize_session=False)
        db.query(UserSettings).filter(UserSettings.user_id == uid).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return templates.TemplateResponse(
        request=request,
        name="settings/delete_data.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "settings",
            "csrf_token": generate_csrf_token(),
            "message": "Your data has been deleted. Note: this deletes data stored in this app but cannot remove text already sent to the AI provider.",
        },
    )
