import uuid

from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import create_session_token, SESSION_COOKIE_NAME, generate_csrf_token
from app.models import User, ImportBatch, Message, Task, Candidate, ExtractionRun, UserSettings
from tests.test_phase6_extraction import _create_user


def _add_data(db, user):
    batch = ImportBatch(user_id=user.id, source_name="t.txt", message_count=1)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    m = Message(batch_id=batch.id, user_id=user.id, text="hello")
    db.add(m)
    db.commit()
    db.refresh(m)
    run = ExtractionRun(batch_id=batch.id, user_id=user.id, model_name="test", prompt_version="1", status="ok")
    db.add(run)
    db.commit()
    db.refresh(run)
    c = Candidate(user_id=user.id, message_id=m.id, run_id=run.id, kind="assignment", title="t", quote="hello")
    db.add(c)
    t = Task(user_id=user.id, title="task", status="pending")
    db.add(t)
    db.commit()


def test_delete_data_removes_only_a_and_keeps_b_and_account_exists(db_session):
    user_a = _create_user(db_session, email=f"a{uuid.uuid4().hex[:6]}@t.com")
    user_b = _create_user(db_session, email=f"b{uuid.uuid4().hex[:6]}@t.com")
    _add_data(db_session, user_a)
    _add_data(db_session, user_b)

    client = TestClient(app, follow_redirects=False)
    token = create_session_token(user_a.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    resp = client.post("/settings/delete-data", data={"csrf_token": generate_csrf_token()})
    assert resp.status_code in (200, 303)

    assert db_session.query(ImportBatch).filter(ImportBatch.user_id == user_a.id).count() == 0
    assert db_session.query(Message).filter(Message.user_id == user_a.id).count() == 0
    assert db_session.query(Candidate).filter(Candidate.user_id == user_a.id).count() == 0
    assert db_session.query(ExtractionRun).filter(ExtractionRun.user_id == user_a.id).count() == 0
    assert db_session.query(Task).filter(Task.user_id == user_a.id).count() == 0
    assert db_session.query(UserSettings).filter(UserSettings.user_id == user_a.id).count() == 0

    assert db_session.query(ImportBatch).filter(ImportBatch.user_id == user_b.id).count() == 1
    assert db_session.query(Message).filter(Message.user_id == user_b.id).count() == 1
    assert db_session.query(Candidate).filter(Candidate.user_id == user_b.id).count() == 1
    assert db_session.query(ExtractionRun).filter(ExtractionRun.user_id == user_b.id).count() == 1
    assert db_session.query(Task).filter(Task.user_id == user_b.id).count() == 1
    assert db_session.query(User).filter(User.id == user_a.id).count() == 1


def test_delete_data_logged_out_redirects_get_and_post():
    client = TestClient(app, follow_redirects=False)
    resp_get = client.get("/settings/delete-data")
    assert resp_get.status_code in (302, 303, 307)
    assert "/auth/login" in resp_get.headers.get("location", "")
    resp_post = client.post("/settings/delete-data", data={"csrf_token": generate_csrf_token()})
    assert resp_post.status_code in (302, 303, 307)
    assert "/auth/login" in resp_post.headers.get("location", "")


def test_delete_data_invalid_csrf_rejected_and_no_deletion(db_session):
    user = _create_user(db_session)
    _add_data(db_session, user)
    client = TestClient(app, follow_redirects=False)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    resp = client.post("/settings/delete-data", data={"csrf_token": "bad"})
    assert resp.status_code == 400
    assert db_session.query(Task).filter(Task.user_id == user.id).count() == 1


def test_landing_logged_out_ok_logged_in_redirects(db_session):
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Turn the messages you already get into a realistic plan" in resp.text
    user = _create_user(db_session)
    client2 = TestClient(app, follow_redirects=False)
    token = create_session_token(user.id)
    client2.cookies.set(SESSION_COOKIE_NAME, token)
    resp2 = client2.get("/")
    assert resp2.status_code in (302, 303, 307)
    assert "/dashboard" in resp2.headers.get("location", "")
