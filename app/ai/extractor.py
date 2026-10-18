from typing import List, Dict, Any
import json
import time

from app.ai import prompts
from app.ai.llm_client import complete_json, LLMUnavailableError
from app.ai.validator import validate_candidates_for_chunk, ValidationError, _validate_with_hallucination_count
from app.models import ImportBatch, Message, ExtractionRun, Candidate
from app.dates.resolver import resolve_deadline


def extract_batch(db, user_id: int, batch_id: int) -> ExtractionRun:
    start = time.time()

    batch = db.query(ImportBatch).filter(
        ImportBatch.id == batch_id,
        ImportBatch.user_id == user_id
    ).first()
    if not batch:
        raise ValueError('Batch not found')

    messages = db.query(Message).filter(
        Message.batch_id == batch_id,
        Message.user_id == user_id
    ).order_by(Message.line_no.asc(), Message.id.asc()).all()

    run = ExtractionRun(
        batch_id=batch_id,
        user_id=user_id,
        model_name=None,
        prompt_version=prompts.PROMPT_VERSION,
        status='ok',
        error_message=None,
        duration_ms=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    chunk_size = 20
    total_hallucinations = 0
    total_chunks_failed = 0

    for i in range(0, len(messages), chunk_size):
        chunk = messages[i:i + chunk_size]
        chunk_halluc, chunk_failed = _process_chunk(db, run, chunk)
        total_hallucinations += chunk_halluc
        if chunk_failed:
            total_chunks_failed += 1

    duration_ms = int((time.time() - start) * 1000)
    run.duration_ms = duration_ms
    db.commit()
    return run


def _process_chunk(db, run: ExtractionRun, chunk: List[Message]) -> tuple[int, bool]:
    hallucination_count = 0
    chunk_failed = False

    chunk_payload = []
    msg_map = {m.id: m for m in chunk}
    for m in chunk:
        chunk_payload.append({
            'id': m.id,
            'timestamp': m.sent_at.isoformat() if m.sent_at else None,
            'text': m.text,
        })

    user_prompt = json.dumps({'messages': chunk_payload}, ensure_ascii=False)

    try:
        response_text = complete_json(prompts.SYSTEM_PROMPT, user_prompt)
    except (LLMUnavailableError, Exception) as e:
        run.status = 'failed'
        run.error_message = str(e)
        db.commit()
        chunk_failed = True
        return (hallucination_count, chunk_failed)

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        repair_prompt = (
            'The previous response was not valid JSON. Return only valid JSON in the exact format '
            '{"candidates": [...]} with all required fields.'
        )
        try:
            response_text2 = complete_json(prompts.SYSTEM_PROMPT + '\n' + repair_prompt, user_prompt)
            data = json.loads(response_text2)
        except Exception:
            chunk_failed = True
            return (hallucination_count, chunk_failed)

    try:
        valid_candidates, hallucination_count = _validate_with_hallucination_count(data, chunk)
    except Exception:
        chunk_failed = True
        return (hallucination_count, chunk_failed)

    for c in valid_candidates:
        msg = msg_map.get(c['message_id'])
        if not msg:
            continue
        deadline_text = c.get('deadline_text')
        if deadline_text:
            deadline_date, deadline_flag = resolve_deadline(deadline_text, msg.sent_at)
        else:
            deadline_date, deadline_flag = (None, 'unresolved')

        is_joke = bool(c.get('is_joke_or_hypothetical'))
        status = 'dismissed' if is_joke else 'pending'
        suppressed_reason = 'joke_or_hypothetical' if is_joke else None

        cand = Candidate(
            user_id=run.user_id,
            message_id=c['message_id'],
            run_id=run.id,
            kind=c['kind'],
            title=c['title'],
            subject=c.get('subject'),
            deadline_text=deadline_text,
            deadline_date=deadline_date,
            deadline_flag=deadline_flag if deadline_flag else ('unresolved' if not deadline_text else 'ok'),
            estimated_hours=c.get('estimated_hours'),
            certainty=c['certainty'],
            quote=c['quote'],
            status=status,
            suppressed_reason=suppressed_reason,
        )
        db.add(cand)

    db.commit()
    return (hallucination_count, chunk_failed)
