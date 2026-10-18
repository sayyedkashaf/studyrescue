"""
Phase 6 tests – Extraction.

Uses a MOCKED llm client only; tests must never call the real API.
"""
from datetime import datetime
from unittest.mock import patch

from app.auth.security import create_session_token, SESSION_COOKIE_NAME, generate_csrf_token
from app.models import User, UserSettings, Message, ImportBatch, ExtractionRun, Candidate
from app.services import batch_service
from app.ai.llm_client import LLMUnavailableError
from fastapi.testclient import TestClient
from app.main import app
def _create_user(db, email='student@example.com'):
    user = User(email=email, password_hash='hash', display_name='Student')
    db.add(user)
    db.commit()
    db.refresh(user)
    settings = UserSettings(user_id=user.id)
    db.add(settings)
    db.commit()
    return user


def _sample_batch_with_msgs(db, user_id):
    batch = ImportBatch(user_id=user_id, source_name='test.txt', message_count=2)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    m1 = Message(batch_id=batch.id, user_id=user_id, sent_at=datetime(2026, 10, 18, 10, 0), text='Submit assignment by tomorrow')
    m2 = Message(batch_id=batch.id, user_id=user_id, sent_at=datetime(2026, 10, 18, 11, 0), text='Exam on 25 Oct')
    db.add(m1)
    db.add(m2)
    db.commit()
    db.refresh(m1)
    db.refresh(m2)
    batch.message_count = 2
    db.commit()
    return batch, [m1, m2]
def test_valid_output_stored_with_resolved_dates(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    mock_resp = '''{"candidates": [
        {"message_id": %d, "kind": "assignment", "title": "Submit assignment", "subject": null, "deadline_text": "tomorrow", "estimated_hours": 2.0, "certainty": "definite", "is_joke_or_hypothetical": false, "quote": "Submit assignment by tomorrow", "reason": "test"},
        {"message_id": %d, "kind": "exam", "title": "Exam", "subject": null, "deadline_text": "25 Oct", "estimated_hours": null, "certainty": "probable", "is_joke_or_hypothetical": false, "quote": "Exam on 25 Oct", "reason": "test"}
    ]}''' % (msgs[0].id, msgs[1].id)

    with patch('app.ai.extractor.complete_json', return_value=mock_resp):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 200

    cands = db_session.query(Candidate).filter(Candidate.user_id == user.id).all()
    assert len(cands) == 2
