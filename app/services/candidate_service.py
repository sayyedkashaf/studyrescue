import re
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models import Candidate, Message


def normalize_title(title: str) -> str:
    """Normalise title: lower case, punctuation and extra spaces removed."""
    t = (title or "").lower()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def list_candidates(db: Session, user_id: int, **filters) -> List[Candidate]:
    q = db.query(Candidate).filter(Candidate.user_id == user_id)
    if filters and 'status' in filters and filters['status'] is not None:
        q = q.filter(Candidate.status == filters['status'])
    return q.order_by(Candidate.created_at.desc()).all()


def get_candidate(db: Session, user_id: int, candidate_id: int) -> Candidate | None:
    return db.query(Candidate).filter(
        Candidate.user_id == user_id,
        Candidate.id == candidate_id
    ).first()


def get_candidates_by_ids(db: Session, user_id: int, candidate_ids: List[int]) -> List[Candidate]:
    if not candidate_ids:
        return []
    return db.query(Candidate).filter(
        Candidate.user_id == user_id,
        Candidate.id.in_(candidate_ids)
    ).all()


def get_pending_candidates_for_batch(db: Session, user_id: int, batch_id: int) -> List[Candidate]:
    return (
        db.query(Candidate)
        .join(Message, Candidate.message_id == Message.id)
        .filter(
            Candidate.user_id == user_id,
            Message.batch_id == batch_id,
            Candidate.status == "pending",
        )
        .order_by(Candidate.id.asc())
        .all()
    )


def group_candidates(candidates: List[Candidate]) -> List[Dict[str, Any]]:
    """
    Group pending candidates in the same batch that have the same normalised title
    and the same resolved date into one card.
    The card lists all their quotes.
    If candidates with the same title have different dates, do not merge them,
    and show them next to each other.
    """
    groups_dict: Dict[tuple, List[Candidate]] = {}
    for c in candidates:
        norm_t = normalize_title(c.title)
        key = (norm_t, c.deadline_date)
        if key not in groups_dict:
            groups_dict[key] = []
        groups_dict[key].append(c)

    # Sort groups so candidates with the same normalized title appear next to each other
    sorted_keys = sorted(
        groups_dict.keys(),
        key=lambda k: (k[0], k[1].isoformat() if k[1] else "")
    )

    result = []
    for key in sorted_keys:
        group_cands = groups_dict[key]
        primary = group_cands[0]

        quotes = []
        for c in group_cands:
            sender = c.message.sender_alias if c.message else "Unknown"
            sent_at = c.message.sent_at if c.message else None
            quotes.append({
                "quote": c.quote,
                "sender_alias": sender,
                "sent_at": sent_at,
            })

        # Flag determination
        if any(c.deadline_flag == "ambiguous" for c in group_cands):
            flag = "ambiguous"
        elif any(c.deadline_flag == "unresolved" for c in group_cands) or primary.deadline_date is None:
            flag = "unresolved" if primary.deadline_date is None else primary.deadline_flag
        else:
            flag = primary.deadline_flag

        # Certainty: if all definite -> definite; if any unclear -> unclear; else probable
        if all(c.certainty == "definite" for c in group_cands):
            certainty = "definite"
        elif any(c.certainty == "unclear" for c in group_cands):
            certainty = "unclear"
        else:
            certainty = "probable"

        result.append({
            "normalized_title": key[0],
            "title": primary.title,
            "subject": primary.subject,
            "kind": primary.kind,
            "deadline_date": primary.deadline_date,
            "deadline_text": primary.deadline_text,
            "deadline_flag": flag,
            "estimated_hours": primary.estimated_hours,
            "certainty": certainty,
            "candidates": group_cands,
            "candidate_ids": [c.id for c in group_cands],
            "candidate_ids_str": ",".join(str(c.id) for c in group_cands),
            "quotes": quotes,
            "primary_id": primary.id,
        })
    return result

