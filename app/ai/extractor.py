import os
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
        model_name=(os.getenv('LLM_MODEL') or os.getenv('LLM_PROVIDER') or 'unknown'),
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


import re

def _clean_and_parse_json(text: str) -> Any:
    if not text:
        raise ValueError("Empty response")
    cleaned = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return {"candidates": parsed}
        return parsed
    except json.JSONDecodeError:
        pass
    start_brace = cleaned.find('{')
    end_brace = cleaned.rfind('}')
    if start_brace != -1 and end_brace > start_brace:
        try:
            return json.loads(cleaned[start_brace:end_brace + 1])
        except json.JSONDecodeError:
            pass
    start_bracket = cleaned.find('[')
    end_bracket = cleaned.rfind(']')
    if start_bracket != -1 and end_bracket > start_bracket:
        try:
            parsed = json.loads(cleaned[start_bracket:end_bracket + 1])
            if isinstance(parsed, list):
                return {"candidates": parsed}
            return parsed
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("Could not extract valid JSON from response", text, 0)


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
    user_prompt = json.dumps(chunk_payload)
    try:
        response_text = complete_json(prompts.SYSTEM_PROMPT, user_prompt)
    except LLMUnavailableError as e:
        # Mark extraction run as failed and re-raise for route handling
        run.status = 'failed'
        run.error_message = str(e)
        db.commit()
        raise
    except Exception as e:
        # Record failure for this chunk but continue processing other chunks
        run.status = 'failed'
        run.error_message = str(e)
        db.commit()
        chunk_failed = True
        return (hallucination_count, chunk_failed)

    try:
        data = _clean_and_parse_json(response_text)
    except Exception:
        repair_prompt = (
            'The previous response was not valid JSON. Return only valid JSON in the exact format '
            '{"candidates": [...]} with all required fields.'
        )
        try:
            response_text2 = complete_json(prompts.SYSTEM_PROMPT + '\n' + repair_prompt, user_prompt)
            data = _clean_and_parse_json(response_text2)
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
            is_joke_or_hypothetical=is_joke,
            status=status,
            suppressed_reason=suppressed_reason,
        )
        db.add(cand)

    db.commit()
    return (hallucination_count, chunk_failed)


def extract_from_messages(messages) -> list[dict]:
    from types import SimpleNamespace
    from datetime import datetime

    def _to_msg(m):
        sent_at = m['sent_at']
        if isinstance(sent_at, str):
            try:
                sent_at = datetime.fromisoformat(sent_at)
            except ValueError:
                sent_at = datetime.fromisoformat(sent_at.replace('Z', '+00:00'))
        return SimpleNamespace(id=m['id'], sent_at=sent_at, text=m['text'])

    chunk_size = 20
    results = []
    for i in range(0, len(messages), chunk_size):
        chunk = [_to_msg(m) for m in messages[i:i + chunk_size]]
        msg_map = {m.id: m for m in chunk}
        chunk_payload = []
        for m in chunk:
            chunk_payload.append({
                'id': m.id,
                'timestamp': m.sent_at.isoformat() if m.sent_at else None,
                'text': m.text,
            })
        user_prompt = json.dumps(chunk_payload)
        try:
            response_text = complete_json(prompts.SYSTEM_PROMPT, user_prompt)
        except LLMUnavailableError:
            raise
        except Exception:
            continue

        try:
            data = _clean_and_parse_json(response_text)
        except Exception:
            repair_prompt = (
                'The previous response was not valid JSON. Return only valid JSON in the exact format '
                '{"candidates": [...]} with all required fields.'
            )
            try:
                response_text2 = complete_json(prompts.SYSTEM_PROMPT + '\n' + repair_prompt, user_prompt)
                data = _clean_and_parse_json(response_text2)
            except Exception:
                continue

        try:
            valid_candidates, _ = _validate_with_hallucination_count(data, chunk)
        except Exception:
            continue

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

            results.append({
                'message_id': c['message_id'],
                'kind': c['kind'],
                'title': c['title'],
                'subject': c.get('subject'),
                'deadline_text': deadline_text,
                'deadline_date': deadline_date,
                'deadline_flag': deadline_flag if deadline_flag else ('unresolved' if not deadline_text else 'ok'),
                'estimated_hours': c.get('estimated_hours'),
                'certainty': c['certainty'],
                'quote': c['quote'],
                'is_joke_or_hypothetical': is_joke,
                'status': status,
                'suppressed_reason': suppressed_reason,
            })
    return results


