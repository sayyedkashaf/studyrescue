"""
Import routes – HTTP handlers for WhatsApp chat and pasted-text imports.

Routes only parse requests, call services, and render templates.
Every route is protected and strictly scoped to the current user.
"""

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import APP_NAME
from app.db import get_db
from app.models import User
from app.auth.deps import get_current_user
from app.auth.security import generate_csrf_token, verify_csrf_token
from app.ingest.text_splitter import is_whatsapp_format, split_pasted_text
from app.ingest.whatsapp_parser import parse_whatsapp_export
from app.services import batch_service

router = APIRouter(prefix="/imports", tags=["imports"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB
READ_CHUNK = 1024 * 1024         # 1 MB chunks while enforcing the cap


def _parse_reference_date(value: str | None) -> date | None:
    """Safely parse an ISO date string (YYYY-MM-DD). Returns None on error or empty."""
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _render_page(
    request: Request,
    current_user: User,
    db: Session,
    *,
    error: str | None = None,
    success: bool = False,
    summary: dict | None = None,
    form_data: dict | None = None,
    status_code: int = 200,
):
    batches = batch_service.list_batches(db, current_user.id)
    return templates.TemplateResponse(
        request=request,
        name="imports/index.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "imports",
            "csrf_token": generate_csrf_token(),
            "batches": batches,
            "summary": summary,
            "success": success,
            "error": error,
            "form_data": form_data or {},
        },
        status_code=status_code,
    )


# ── Import Page ───────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def imports_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Renders the import form and the list of previous imports."""
    return _render_page(request, current_user, db)


@router.post("", response_class=HTMLResponse)
@router.post("/", response_class=HTMLResponse)
def import_endpoint(
    request: Request,
    paste_text: str = Form(""),
    reference_date: str = Form(""),
    upload_file: UploadFile | None = File(None),
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Validates input, parses/imports messages, and shows a summary."""
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    form_data = {"paste_text": paste_text, "reference_date": reference_date}
    error: str | None = None

    has_file = upload_file is not None and getattr(upload_file, "filename", "") not in ("", None)
    raw_text: str | None = None
    source_name = "Pasted Text"

    if has_file and paste_text.strip():
        error = "Please either paste text or upload a file, not both."

    # ── File upload path ──────────────────────────────────────────────
    if not error and has_file:
        filename = upload_file.filename or ""
        if not filename.lower().endswith(".txt"):
            error = "Only .txt files are allowed."
        else:
            total = 0
            chunks: list[bytes] = []
            oversize = False
            while True:
                chunk = upload_file.file.read(READ_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    oversize = True
                    break
                chunks.append(chunk)
            if oversize:
                error = "File is too large. Maximum size is 2 MB."
            else:
                raw_bytes = b"".join(chunks)
                try:
                    raw_text = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    error = "File must be valid UTF-8 text."
                if not error and not raw_text.strip():
                    error = "The uploaded file is empty."
                source_name = filename

    # ── Paste path ────────────────────────────────────────────────────
    if not error and not has_file:
        if not paste_text or not paste_text.strip():
            error = "Please paste some text or upload a .txt file."
        else:
            raw_text = paste_text

    if error:
        return _render_page(
            request, current_user, db, error=error, form_data=form_data, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )

    # ── Parse ─────────────────────────────────────────────────────────
    reference = _parse_reference_date(reference_date)
    if is_whatsapp_format(raw_text or ""):
        messages = parse_whatsapp_export(raw_text or "")
    else:
        messages = split_pasted_text(raw_text or "", reference)

    if not messages:
        return _render_page(
            request,
            current_user,
            db,
            error="No messages could be parsed from the input. Check that the text contains dated WhatsApp messages (e.g. '12/10/26, 4:15 pm - Name: message').",
            form_data=form_data,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    batch = batch_service.create_batch(
        db=db, user_id=current_user.id, source_name=source_name, messages=messages
    )
    summary = batch_service.get_batch_summary(db, current_user.id, batch.id)
    return _render_page(request, current_user, db, success=True, summary=summary)


# ── Delete (with confirmation step) ───────────────────────────────────

@router.get("/{batch_id}/delete", response_class=HTMLResponse)
def delete_import_confirmation_page(
    batch_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Presents a confirmation page before deleting the import batch."""
    batch = batch_service.get_batch(db, current_user.id, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found")

    return templates.TemplateResponse(
        request=request,
        name="imports/delete.html",
        context={
            "app_name": APP_NAME,
            "current_user": current_user,
            "active_page": "imports",
            "csrf_token": generate_csrf_token(),
            "batch": batch,
        },
    )


@router.post("/{batch_id}/delete")
def delete_import_endpoint(
    batch_id: int,
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deletes an import batch. Returns 404 if not found or owned by another user."""
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    success = batch_service.delete_batch(db, current_user.id, batch_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found")

    return RedirectResponse(url="/imports", status_code=status.HTTP_303_SEE_OTHER)
# Add after delete endpoint
@router.post("/{batch_id}/extract")
def extract_tasks_endpoint(
    batch_id: int,
    request: Request,
    csrf_token: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger AI extraction for a batch. Prevents running twice concurrently."""
    if not verify_csrf_token(csrf_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid security token")

    from datetime import datetime as _dt, timedelta
    from app.ai import extractor
    from app.ai.llm_client import LLMUnavailableError
    from app.services import candidate_service

    user_id = getattr(current_user, "id", None) or getattr(current_user, "_id", None)
    batch = batch_service.get_batch(db, user_id, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found")

    # Prevent running extraction twice on the same batch at once,
    # but treat runs older than 5 minutes as stale.
    from app.models import ExtractionRun
    if batch.status == 'extracting':
        latest_run = db.query(ExtractionRun).filter(
            ExtractionRun.batch_id == batch_id,
            ExtractionRun.user_id == user_id,
        ).order_by(ExtractionRun.created_at.desc()).first()
        stale_cutoff = _dt.utcnow() - timedelta(minutes=5)
        if latest_run and latest_run.created_at and latest_run.created_at > stale_cutoff:
            # Genuinely still running – block
            return _render_page(
                request, current_user, db,
                error="Extraction is already in progress. Please wait a few minutes.",
                status_code=status.HTTP_409_CONFLICT,
            )
        # Stale – mark the old run as failed and reset batch status to allow re-run
        if latest_run:
            latest_run.status = 'failed'
            latest_run.error_message = 'Extraction run timed out / was stuck on extracting; reset by user retry.'
            db.add(latest_run)
        batch.status = 'failed'
        db.commit()

    try:
        # Set batch status to extracting
        batch.status = 'extracting'
        db.commit()

        run = extractor.extract_batch(db, user_id, batch_id)

        # Count results
        candidates = candidate_service.list_candidates(db, user_id)
        run_candidates = [c for c in candidates if c.run_id == run.id]

        candidates_found = len(run_candidates)
        suppressed_jokes = sum(1 for c in run_candidates if c.is_joke_or_hypothetical and c.suppressed_reason == 'joke_or_hypothetical')

        extraction_summary = {
            'candidates_found': candidates_found,
            'suppressed_jokes': suppressed_jokes,
            'hallucinations_rejected': 0,
            'chunks_failed': 0 if run.status != 'failed' else 1,
            'candidates': run_candidates,
            'run': run,
        }
        # Mark batch as done on success (or failed if the run had chunk errors)
        batch.status = 'done' if run.status != 'failed' else 'failed'
        db.commit()
        return _render_extraction_summary(request, current_user, db, batch_id, extraction_summary)
    except LLMUnavailableError:
        return templates.TemplateResponse(
            request=request,
            name='imports/extraction_summary.html',
            context={
                'app_name': APP_NAME,
                'current_user': current_user,
                'active_page': 'imports',
                'csrf_token': generate_csrf_token(),
                'batch': batch,
                'error': 'AI extraction is temporarily unavailable. You can add tasks manually.',
                'summary': {
                    'candidates_found': 0,
                    'suppressed_jokes': 0,
                    'hallucinations_rejected': 0,
                    'chunks_failed': 0,
                    'candidates': [],
                },
            },
            status_code=200,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # ALWAYS reset batch status – never leave it stuck on 'extracting'
        db.refresh(batch)
        if batch.status == 'extracting':
            batch.status = 'failed'
            # Also mark the latest run as failed so it isn't left dangling
            latest_run = db.query(ExtractionRun).filter(
                ExtractionRun.batch_id == batch_id,
                ExtractionRun.user_id == user_id,
            ).order_by(ExtractionRun.created_at.desc()).first()
            if latest_run:
                latest_run.status = 'failed'
                latest_run.error_message = 'Extraction run did not complete; status reset to failed.'
                db.add(latest_run)
            db.commit()


def _render_extraction_summary(request, current_user, db, batch_id, extraction_summary):
    batch = batch_service.get_batch(db, current_user.id, batch_id)
    return templates.TemplateResponse(
        request=request,
        name='imports/extraction_summary.html',
        context={
            'app_name': APP_NAME,
            'current_user': current_user,
            'active_page': 'imports',
            'csrf_token': generate_csrf_token(),
            'batch': batch,
            'summary': extraction_summary,
            'candidates': extraction_summary['candidates'],
        }
    )
