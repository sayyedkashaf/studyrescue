from typing import List, Dict, Any, Tuple
import re

try:
    from pydantic import BaseModel, ValidationError as PydanticValidationError, field_validator
except Exception:
    BaseModel = object  # type: ignore
    PydanticValidationError = Exception  # type: ignore


class ValidationError(Exception):
    pass


class CandidateModel(BaseModel):
    message_id: int
    kind: str
    title: str
    subject: str | None = None
    deadline_text: str | None = None
    estimated_hours: float | None = None
    certainty: str
    is_joke_or_hypothetical: bool = False
    quote: str
    reason: str | None = None

    @field_validator('kind')
    @classmethod
    def _validate_kind(cls, v):
        if v not in ('assignment', 'exam', 'submission', 'other'):
            raise ValueError('invalid kind')
        return v

    @field_validator('certainty')
    @classmethod
    def _validate_certainty(cls, v):
        if v not in ('definite', 'probable', 'unclear'):
            raise ValueError('invalid certainty')
        return v

    @field_validator('title')
    @classmethod
    def _validate_title(cls, v):
        if not v or not str(v).strip():
            raise ValueError('invalid title')
        return str(v).strip()[:80]

    @field_validator('quote')
    @classmethod
    def _validate_quote(cls, v):
        if not v:
            raise ValueError('invalid quote')
        return v


def _normalize_text_for_match(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip().lower()


def validate_candidates_for_chunk(
    data: Dict[str, Any],
    chunk: List[Any]
) -> List[Dict[str, Any]]:
    valid, _ = _validate_with_hallucination_count(data, chunk)
    return valid


def _validate_with_hallucination_count(
    data: Dict[str, Any],
    chunk: List[Any]
) -> Tuple[List[Dict[str, Any]], int]:
    if not isinstance(data, dict) or 'candidates' not in data:
        raise ValidationError('invalid response structure')

    candidates = data.get('candidates')
    if not isinstance(candidates, list):
        raise ValidationError('candidates must be list')

    chunk_msg_ids = set(m.id for m in chunk)
    msg_map = {m.id: m for m in chunk}
    valid = []
    hallucination_count = 0

    for c in candidates:
        try:
            if BaseModel is not object:
                cm = CandidateModel.model_validate(c)  # type: ignore
                c_dict = cm.model_dump()
            else:
                if not isinstance(c.get('message_id'), int):
                    continue
                if c.get('kind') not in ('assignment', 'exam', 'submission', 'other'):
                    continue
                if c.get('certainty') not in ('definite', 'probable', 'unclear'):
                    continue
                title = str(c.get('title') or '').strip()
                if not title:
                    continue
                quote = str(c.get('quote') or '')
                if not quote:
                    continue
                est = c.get('estimated_hours')
                if isinstance(est, bool):
                    est = None
                elif not isinstance(est, (int, float)) and est is not None:
                    est = None
                c_dict = {
                    'message_id': c['message_id'],
                    'kind': c['kind'],
                    'title': title[:80],
                    'subject': c.get('subject') if isinstance(c.get('subject'), str) or c.get('subject') is None else str(c.get('subject')),
                    'deadline_text': c.get('deadline_text') if isinstance(c.get('deadline_text'), str) or c.get('deadline_text') is None else str(c.get('deadline_text')),
                    'estimated_hours': est,
                    'certainty': c['certainty'],
                    'is_joke_or_hypothetical': bool(c.get('is_joke_or_hypothetical')),
                    'quote': quote,
                    'reason': c.get('reason') if isinstance(c.get('reason'), str) or c.get('reason') is None else str(c.get('reason')),
                }
        except Exception:
            continue

        if c_dict['message_id'] not in chunk_msg_ids:
            continue

        msg = msg_map.get(c_dict['message_id'])
        if not msg:
            continue

        src_norm = _normalize_text_for_match(msg.text)
        q_norm = _normalize_text_for_match(c_dict['quote'])
        if q_norm not in src_norm:
            hallucination_count += 1
            continue  # reject and count hallucination

        valid.append(c_dict)

    return valid, hallucination_count
