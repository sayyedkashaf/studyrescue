from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models import Candidate


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
