"""
Review and Confirmation routes – Phase 7.

Enables human-in-the-loop review of AI-extracted task candidates before they become tasks.
No candidate becomes a task without the student's explicit confirmation.
"""

from datetime import date
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.config import APP_NAME
from app.db import get_db
from app.models import User, Candidate
from app.auth.deps import get_current_user
from app.auth.security import generate_csrf_token, verify_csrf_token
from app.services import batch_service, candidate_service, task_service

router = APIRouter(prefix="/review", tags=["review"])

_base = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(_base / "templates"))


def _parse_date(val: str | None) -> date | None:
    if not val or not val.strip():
        return None
    try:
        return date.fromisoformat(val.strip())
    except ValueError:
        return None


def _parse_float(val: str | None) -> float | None:
    if not val or not val.strip():
        return None
    try:
        return float(val.strip())
    except ValueError:
        return None


@router.get("/{batch_id}", response_class=HTMLResponse)
def get_review_batch(
    batch_id: int,
    request: Request,
    info: str | None = None,
    warning: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List pending candidates for the specified batch, grouped into cards."""
    batch = batch_service.get_batch(db, current_user.id, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found")

    pending_cands = candidate_service.get_pending_candidates_for_batch(db, current_user.id, batch_id)
    cards = candidate_service.group_candidates(pending_cands)

    definite_count = sum(
        1 for card in cards
        if all(c.certainty == "definite" and c.deadline_flag == "ok" for c in card["candidates"])
    )

    return templates.TemplateResponse(
        request=request,
        name="review/index.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "imports",
            "csrf_token": generate_csrf_token(),
            "batch": batch,
            "cards": cards,
            "has_definite": definite_count > 0,
            "info": info,
            "warning": warning,
        },
    )


@router.post("/{batch_id}/confirm")
def confirm_candidate_post(
    batch_id: int,
    request: Request,
    candidate_ids: str = Form(""),
    title: str = Form(""),
    subject: str = Form(""),
    kind: str = Form("assignment"),
    deadline: str = Form(""),
    estimated_hours: str = Form(""),
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm one candidate (or duplicate group), creating exactly one task."""
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    batch = batch_service.get_batch(db, current_user.id, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found")

    # Parse candidate IDs
    try:
        c_ids = [int(x.strip()) for x in candidate_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid candidate IDs")

    if not c_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No candidate IDs provided")

    cands = candidate_service.get_candidates_by_ids(db, current_user.id, c_ids)
    if len(cands) != len(c_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidates not found")

    # Verify that all candidates belong to this batch
    for c in cands:
        if not c.message or c.message.batch_id != batch_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate does not belong to this batch")

    primary = cands[0]
    parsed_deadline = _parse_date(deadline)
    parsed_hours = _parse_float(estimated_hours)
    quotes_text = "\n".join(f'"{c.quote}"' for c in cands)

    task_service.create_task(
        db=db,
        user_id=current_user.id,
        title=title.strip() or primary.title,
        description=quotes_text,
        subject=subject.strip() or None,
        kind=kind.strip().lower() or "assignment",
        deadline=parsed_deadline,
        estimated_hours=parsed_hours,
        source="extracted",
        candidate_id=primary.id,
    )

    for c in cands:
        c.status = "confirmed"
    db.commit()

    url = f"/review/{batch_id}"
    if parsed_deadline is None:
        url += "?warning=" + quote("Task created without a deadline.")
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{batch_id}/confirm/{candidate_id}")
def confirm_single_candidate_shortcut(
    batch_id: int,
    candidate_id: int,
    request: Request,
    title: str = Form(""),
    subject: str = Form(""),
    kind: str = Form("assignment"),
    deadline: str = Form(""),
    estimated_hours: str = Form(""),
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Shortcut endpoint to confirm a single candidate by path parameter."""
    return confirm_candidate_post(
        batch_id=batch_id,
        request=request,
        candidate_ids=str(candidate_id),
        title=title,
        subject=subject,
        kind=kind,
        deadline=deadline,
        estimated_hours=estimated_hours,
        csrf_token=csrf_token,
        current_user=current_user,
        db=db,
    )


@router.post("/{batch_id}/dismiss")
def dismiss_candidate_post(
    batch_id: int,
    request: Request,
    candidate_ids: str = Form(""),
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dismiss one candidate (or duplicate group)."""
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    batch = batch_service.get_batch(db, current_user.id, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found")

    try:
        c_ids = [int(x.strip()) for x in candidate_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid candidate IDs")

    if not c_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No candidate IDs provided")

    cands = candidate_service.get_candidates_by_ids(db, current_user.id, c_ids)
    if len(cands) != len(c_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidates not found")

    for c in cands:
        if not c.message or c.message.batch_id != batch_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate does not belong to this batch")
        c.status = "dismissed"

    db.commit()
    return RedirectResponse(url=f"/review/{batch_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{batch_id}/dismiss/{candidate_id}")
def dismiss_single_candidate_shortcut(
    batch_id: int,
    candidate_id: int,
    request: Request,
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Shortcut endpoint to dismiss a single candidate by path parameter."""
    return dismiss_candidate_post(
        batch_id=batch_id,
        request=request,
        candidate_ids=str(candidate_id),
        csrf_token=csrf_token,
        current_user=current_user,
        db=db,
    )


@router.post("/{batch_id}/confirm-definite")
def confirm_all_definite_endpoint(
    batch_id: int,
    request: Request,
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Bulk confirm all candidates that have certainty 'definite' AND deadline_flag 'ok'.
    Never touches unclear, probable, ambiguous or unresolved candidates.
    """
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    batch = batch_service.get_batch(db, current_user.id, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found")

    pending_cands = candidate_service.get_pending_candidates_for_batch(db, current_user.id, batch_id)
    groups = candidate_service.group_candidates(pending_cands)

    confirmed_count = 0
    for group in groups:
        group_cands = group["candidates"]
        is_definite_and_ok = all(
            c.certainty == "definite" and c.deadline_flag == "ok"
            for c in group_cands
        )
        if is_definite_and_ok:
            primary = group_cands[0]
            quotes_text = "\n".join(f'"{c.quote}"' for c in group_cands)
            task_service.create_task(
                db=db,
                user_id=current_user.id,
                title=primary.title,
                description=quotes_text,
                subject=primary.subject,
                kind=primary.kind,
                deadline=primary.deadline_date,
                estimated_hours=primary.estimated_hours,
                source="extracted",
                candidate_id=primary.id,
            )
            for c in group_cands:
                c.status = "confirmed"
            confirmed_count += len(group_cands)

    db.commit()

    remaining_pending = candidate_service.get_pending_candidates_for_batch(db, current_user.id, batch_id)
    remaining_count = len(remaining_pending)

    msg = f"Confirmed {confirmed_count} candidate(s). {remaining_count} left for manual review."
    url = f"/review/{batch_id}?info=" + quote(msg)
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
