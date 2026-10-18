"""
Phase 6 tests – Extraction.

Uses a MOCKED llm client only; tests must never call the real API.
"""
from datetime import datetime, date
import json
from unittest.mock import patch

from app.auth.security import create_session_token, SESSION_COOKIE_NAME, generate_csrf_token
from app.models import User, UserSettings, Message, ImportBatch, ExtractionRun, Candidate
from app.services import batch_service
from app.ai.llm_client import LLMUnavailableError
from fastapi.testclient import TestClient
from app.main import app
import uuid
def _create_user(db, email=None):
    email = email or f"student-{uuid.uuid4().hex[:8]}@example.com"
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
    # Verify resolved dates and flags
    # First candidate: "tomorrow" -> 2026-10-19, flag ok
    assert cands[0].deadline_date == date(2026, 10, 19)
    assert cands[0].deadline_flag == "ok"
    # Second candidate: "25 Oct" -> 2026-10-25, flag ok
    assert cands[1].deadline_date == date(2026, 10, 25)
    assert cands[1].deadline_flag == "ok"
def test_quote_not_in_message_rejected(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    mock_resp = '''{\"candidates\": [
        {\"message_id\": %d, \"kind\": \"assignment\", \"title\": \"Fake\", \"subject\": null, \"deadline_text\": null, \"estimated_hours\": null, \"certainty\": \"unclear\", \"is_joke_or_hypothetical\": false, \"quote\": \"this quote is not in the message\", \"reason\": \"test\"}
    ]}''' % msgs[0].id
    with patch('app.ai.extractor.complete_json', return_value=mock_resp):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 200
    cands = db_session.query(Candidate).filter(Candidate.user_id == user.id).all()
    assert len(cands) == 0


def test_invalid_json_then_repair_works(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    bad = '{ invalid json'
    good = '''{\"candidates\": [
        {\"message_id\": %d, \"kind\": \"assignment\", \"title\": \"HW\", \"subject\": null, \"deadline_text\": null, \"estimated_hours\": null, \"certainty\": \"definite\", \"is_joke_or_hypothetical\": false, \"quote\": \"Submit assignment by tomorrow\", \"reason\": \"ok\"}
    ]}''' % msgs[0].id
    with patch('app.ai.extractor.complete_json', side_effect=[bad, good]):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 200
    cands = db_session.query(Candidate).filter(Candidate.user_id == user.id).all()
    assert len(cands) == 1


def test_repair_also_fails_chunk_marked_failed_no_crash(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    bad = '{ invalid'
    bad2 = '{ also bad'
    with patch('app.ai.extractor.complete_json', side_effect=[bad, bad2]):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 200
    runs = db_session.query(ExtractionRun).filter(ExtractionRun.batch_id == batch.id).all()
    assert len(runs) >= 1


def test_joke_candidate_suppressed(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    mock_resp = '''{\"candidates\": [
        {\"message_id\": %d, \"kind\": \"assignment\", \"title\": \"Joke\", \"subject\": null, \"deadline_text\": \"tomorrow\", \"estimated_hours\": null, \"certainty\": \"unclear\", \"is_joke_or_hypothetical\": true, \"quote\": \"Submit assignment by tomorrow\", \"reason\": \"joke\"}
    ]}''' % msgs[0].id
    with patch('app.ai.extractor.complete_json', return_value=mock_resp):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 200
    cands = db_session.query(Candidate).filter(Candidate.user_id == user.id).all()
    assert len(cands) == 1
    assert cands[0].status == 'dismissed'
    assert cands[0].suppressed_reason == 'joke_or_hypothetical'


def test_unknown_message_id_rejected(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    mock_resp = '''{\"candidates\": [
        {\"message_id\": 999999, \"kind\": \"assignment\", \"title\": \"Bad\", \"subject\": null, \"deadline_text\": null, \"estimated_hours\": null, \"certainty\": \"unclear\", \"is_joke_or_hypothetical\": false, \"quote\": \"Submit assignment by tomorrow\", \"reason\": \"bad\"}
    ]}'''
    with patch('app.ai.extractor.complete_json', return_value=mock_resp):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 200
    cands = db_session.query(Candidate).filter(Candidate.user_id == user.id).all()
    assert len(cands) == 0


def test_llm_unavailable_error_handled(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    with patch('app.ai.extractor.complete_json', side_effect=LLMUnavailableError('temp down')):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 200
        assert 'AI extraction is temporarily unavailable' in resp.text


def test_user_b_cannot_extract_or_view_user_a_batch(db_session):
    user_a = _create_user(db_session, email='a@test.com')
    user_b = _create_user(db_session, email='b@test.com')
    batch, msgs = _sample_batch_with_msgs(db_session, user_a.id)
    client_b = TestClient(app)
    token_b = create_session_token(user_b.id)
    client_b.cookies.set(SESSION_COOKIE_NAME, token_b)
    mock_resp = '''{\"candidates\": []}'''
    with patch('app.ai.extractor.complete_json', return_value=mock_resp):
        resp = client_b.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 404


def test_no_keyword_prefiltering(db_session):
    user = _create_user(db_session)
    batch = ImportBatch(user_id=user.id, source_name='test.txt', message_count=1)
    db_session.add(batch)
    db_session.commit()
    db_session.refresh(batch)
    m = Message(batch_id=batch.id, user_id=user.id, sent_at=datetime(2026, 10, 18, 10, 0), text='I need to submit the lab record by Friday')
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    mock_resp = '''{\"candidates\": [
        {\"message_id\": %d, \"kind\": \"assignment\", \"title\": \"Lab record\", \"subject\": null, \"deadline_text\": \"Friday\", \"estimated_hours\": null, \"certainty\": \"definite\", \"is_joke_or_hypothetical\": false, \"quote\": \"I need to submit the lab record by Friday\", \"reason\": \"test\"}
    ]}''' % m.id
    with patch('app.ai.extractor.complete_json', return_value=mock_resp):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 200
    cands = db_session.query(Candidate).filter(Candidate.user_id == user.id).all()
    assert len(cands) == 1


def test_extraction_run_logged_with_fields(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    mock_resp = '''{\"candidates\": []}'''
    with patch('app.ai.extractor.complete_json', return_value=mock_resp):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 200
    runs = db_session.query(ExtractionRun).filter(ExtractionRun.batch_id == batch.id, ExtractionRun.user_id == user.id).all()
    assert len(runs) == 1
    r = runs[0]
    assert r.prompt_version is not None
    assert r.status is not None
    assert r.duration_ms is not None


def test_stale_extraction_allows_retry(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    batch.status = 'extracting'
    db_session.commit()

    from datetime import timedelta
    stale_run = ExtractionRun(
        batch_id=batch.id,
        user_id=user.id,
        model_name='test-model',
        prompt_version='1.0',
        status='running',
        created_at=datetime.utcnow() - timedelta(minutes=6),
    )
    db_session.add(stale_run)
    db_session.commit()

    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    mock_resp = '{"candidates": []}'
    with patch('app.ai.extractor.complete_json', return_value=mock_resp):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code != 409
        assert resp.status_code == 200


def test_active_extraction_blocks_retry(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    batch.status = 'extracting'
    db_session.commit()

    from datetime import timedelta
    active_run = ExtractionRun(
        batch_id=batch.id,
        user_id=user.id,
        model_name='test-model',
        prompt_version='1.0',
        status='running',
        created_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db_session.add(active_run)
    db_session.commit()

    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
    assert resp.status_code == 409


def test_extraction_failure_resets_batch_status(db_session):
    user = _create_user(db_session)
    batch, msgs = _sample_batch_with_msgs(db_session, user.id)
    batch.status = 'extracting'
    db_session.commit()

    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    with patch('app.ai.extractor.complete_json', side_effect=LLMUnavailableError('temporarily down')):
        resp = client.post(f'/imports/{batch.id}/extract', data={'csrf_token': generate_csrf_token()})
        assert resp.status_code == 200

    db_session.refresh(batch)
    assert batch.status == 'failed'

