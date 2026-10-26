from pathlib import Path
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import APP_NAME
from app.auth.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

_RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "results"


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def evaluation_page(request: Request, current_user: User = Depends(get_current_user)):
    results = None
    if _RESULTS_DIR.exists():
        json_files = sorted(_RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if json_files:
            with open(json_files[0], encoding="utf-8") as f:
                results = json.load(f)
    if results is None:
        return templates.TemplateResponse(
            request=request,
            name="evaluation/index.html",
            context={
                "app_name": APP_NAME,
                "current_user": current_user,
                "active_page": "evaluation",
                "results": None,
            },
        )
    return templates.TemplateResponse(
        request=request,
        name="evaluation/index.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "evaluation",
            "results": results,
        },
    )
