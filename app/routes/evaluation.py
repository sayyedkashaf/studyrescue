from pathlib import Path
import glob as _glob

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import APP_NAME
from app.auth.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

_REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "reports"


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def evaluation_page(request: Request, current_user: User = Depends(get_current_user)):
    report_text = None
    md_files = sorted(_REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if _REPORTS_DIR.exists() else []
    if md_files:
        report_text = md_files[0].read_text(encoding="utf-8")
    else:
        report_text = "No evaluation report yet. Run eval/run_eval.py."
    return templates.TemplateResponse(
        request=request,
        name="evaluation/index.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "evaluation",
            "report_text": report_text,
        },
    )
