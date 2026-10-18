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
    kind: str = "other"
    title: str = "Untitled Task"
    subject: str | None = None
    deadline_text: str | None = None
    estimated_hours: float | None = None
    certainty: str = "unclear"
    is_joke_or_hypothetical: bool = False
    quote: str
    reason: str | None = None

    @field_validator('message_id', mode='before')
    @classmethod
    def _validate_message_id(cls, v):
        try:
            return int(v)
        except Exception:
            raise ValueError('invalid message_id')

    @field_validator('kind', mode='before')
    @classmethod
    def _validate_kind(cls, v):
        v = str(v or '').strip().lower()
        if v not in ('assignment', 'exam', 'submission', 'other'):
            return 'other'
        return v

    @field_validator('certainty', mode='before')
    @classmethod
    def _validate_certainty(cls, v):
        v = str(v or '').strip().lower()
        if v not in ('definite', 'probable', 'unclear'):
            return 'unclear'
        return v

    @field_validator('title', mode='before')
    @classmethod
    def _validate_title(cls, v):
        s = str(v or '').strip()
        if not s:
            return 'Untitled Task'
        return s[:80]

    @field_validator('estimated_hours', mode='before')
    @classmethod
    def _validate_estimated_hours(cls, v):
        if v is None or v == '' or str(v).strip().lower() in ('null', 'none', 'n/a'):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        try:
            m = re.search(r'(\d+(?:\.\d+)?)', str(v))
            if m:
                return float(m.group(1))
            return None
        except Exception:
            return None

    @field_validator('is_joke_or_hypothetical', mode='before')
    @classmethod
    def _validate_joke(cls, v):
        if isinstance(v, str):
            return v.strip().lower() in ('true', '1', 'yes')
        return bool(v)

    @field_validator('quote', mode='before')
    @classmethod
    def _validate_quote(cls, v):
        s = str(v or '').strip()
        if not s:
            raise ValueError('invalid quote')
        return s


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
        if not isinstance(c, dict):
            continue
        try:
            if BaseModel is not object:
                cm = CandidateModel.model_validate(c)  # type: ignore
                c_dict = cm.model_dump()
            else:
                try:
                    msg_id = int(c.get('message_id'))
                except Exception:
                    continue
                kind = str(c.get('kind') or '').strip().lower()
                if kind not in ('assignment', 'exam', 'submission', 'other'):
                    kind = 'other'
                certainty = str(c.get('certainty') or '').strip().lower()
                if certainty not in ('definite', 'probable', 'unclear'):
                    certainty = 'unclear'
                title = str(c.get('title') or '').strip() or 'Untitled Task'
                quote = str(c.get('quote') or '').strip()
                if not quote:
                    continue
                est = c.get('estimated_hours')
                if est is not None and not isinstance(est, (int, float)):
                    m = re.search(r'(\d+(?:\.\d+)?)', str(est))
                    est = float(m.group(1)) if m else None
                elif isinstance(est, (int, float)):
                    est = float(est)
                else:
                    est = None
                joke_raw = c.get('is_joke_or_hypothetical')
                if isinstance(joke_raw, str):
                    joke_val = joke_raw.strip().lower() in ('true', '1', 'yes')
                else:
                    joke_val = bool(joke_raw)
                c_dict = {
                    'message_id': msg_id,
                    'kind': kind,
                    'title': title[:80],
                    'subject': c.get('subject') if isinstance(c.get('subject'), str) or c.get('subject') is None else str(c.get('subject')),
                    'deadline_text': c.get('deadline_text') if isinstance(c.get('deadline_text'), str) or c.get('deadline_text') is None else str(c.get('deadline_text')),
                    'estimated_hours': est,
                    'certainty': certainty,
                    'is_joke_or_hypothetical': joke_val,
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
