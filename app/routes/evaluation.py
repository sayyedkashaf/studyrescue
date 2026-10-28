from pathlib import Path
import csv
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
_LABELED_CSV = Path(__file__).resolve().parent.parent.parent / "eval" / "labeled" / "labeled_messages.csv"


def _compute_baseline_metrics(csv_path: str):
    """Compute keyword and tfidf baseline PRF metrics from the labeled CSV."""
    try:
        from eval.baselines import keyword_baseline_predict, evaluate_tfidf_logreg, train_tfidf_logreg
        from eval.metrics import prf
        from eval.run_eval import confusion, prf_from_cm

        rows = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        if not rows:
            return None

        test_rows = [r for r in rows if r.get("split") == "test"]
        if not test_rows:
            test_rows = rows

        gold = [r.get("gold_label") == "commitment" for r in test_rows]

        # Keyword baseline (use message_text column if text is absent)
        kpred = [keyword_baseline_predict(r.get("text") or r.get("message_text") or "") for r in test_rows]
        kcm = confusion(gold, kpred)
        kp = prf_from_cm(kcm)

        # TF-IDF baseline
        train_rows = [r for r in rows if r.get("split") == "dev"]
        pipe = train_tfidf_logreg(train_rows) if train_rows else None
        tpred = []
        for r in test_rows:
            if pipe:
                try:
                    tpred.append(bool(pipe.predict([r.get("text") or r.get("message_text") or ""])[0]))
                except Exception:
                    tpred.append(False)
            else:
                tpred.append(False)
        tcm = confusion(gold, tpred)
        tp = prf_from_cm(tcm)

        return {
            "keyword": kp,
            "tfidf": tp,
        }
    except Exception:
        return None


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def evaluation_page(request: Request, current_user: User = Depends(get_current_user)):
    results = None
    if _RESULTS_DIR.exists():
        json_files = sorted(_RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if json_files:
            with open(json_files[0], encoding="utf-8") as f:
                results = json.load(f)

    baseline_metrics = None
    if _LABELED_CSV.exists():
        baseline_metrics = _compute_baseline_metrics(str(_LABELED_CSV))

    if results is None and baseline_metrics is None:
        return templates.TemplateResponse(
            request=request,
            name="evaluation/index.html",
            context={
                "app_name": APP_NAME,
                "current_user": current_user,
                "active_page": "evaluation",
                "results": None,
                "baseline_metrics": None,
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
            "baseline_metrics": baseline_metrics,
        },
    )
