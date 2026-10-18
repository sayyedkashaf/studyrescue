"""
Phase 7 tests – Review and confirmation.

Tests human-in-the-loop candidate review, grouping of duplicates,
card editing and task creation, dismissals, bulk confirmation, user isolation,
and empty state. No real LLM calls.
"""

from datetime import datetime, date
import uuid
from fastapi.testclient import TestClient

from app.main import app
from app.auth.security import create_session_token, SESSION_COOKIE_NAME, generate_csrf_token
from app.models import User, UserSettings, Message, ImportBatch, Candidate, Task, TaskHistory
from app.services import candidate_service


def _create_user(db, email=None):
    email = email or f"student-{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash="hash", display_name="Student")
    db.add(user)
    db.commit()
    db.refresh(user)
    settings = UserSettings(user_id=user.id)
    db.add(settings)
    db.commit()
    return user


def _create_batch_and_messages(db, user_id, count=2):
    batch = ImportBatch(user_id=user_id, source_name="chat.txt", message_count=count)
    db.add(batch)
    db.commit()
    db.refresh(batch)

    msgs = []
    for i in range(count):
        m = Message(
            batch_id=batch.id,
            user_id=user_id,
            line_no=i + 1,
            sender_alias=f"Student {i+1}",
            sent_at=datetime(2026, 10, 18, 10 + i, 0),
            text=f"Sample message {i+1}",
        )
        db.add(m)
        msgs.append(m)
    db.commit()
    for m in msgs:
        db.refresh(m)
    return batch, msgs


def _create_candidate(
    db,
    user_id,
    message_id,
    title="Data Mining Assignment 1",
    kind="assignment",
    subject="Data Mining",
    deadline_text="tomorrow",
    deadline_date=date(2026, 10, 19),
    deadline_flag="ok",
    estimated_hours=2.5,
    certainty="definite",
    quote="Submit assignment by tomorrow",
    status="pending",
):
    cand = Candidate(
        user_id=user_id,
        message_id=message_id,
        kind=kind,
        title=title,
        subject=subject,
        deadline_text=deadline_text,
        deadline_date=deadline_date,
        deadline_flag=deadline_flag,
        estimated_hours=estimated_hours,
        certainty=certainty,
        quote=quote,
        is_joke_or_hypothetical=False,
        status=status,
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    return cand


def _make_client(user_id, follow_redirects=False):
    client = TestClient(app, follow_redirects=follow_redirects)
    token = create_session_token(user_id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    return client


def test_confirm_creates_task_with_history_and_marks_confirmed(db_session):
    user = _create_user(db_session)
    batch, msgs = _create_batch_and_messages(db_session, user.id, count=1)
    cand = _create_candidate(
        db_session,
        user.id,
        msgs[0].id,
        title="Web Dev Project",
        subject="CS301",
        kind="assignment",
        deadline_date=date(2026, 10, 25),
        estimated_hours=3.0,
        quote="Project due on 25th",
    )

    client = _make_client(user.id, follow_redirects=False)

    csrf = generate_csrf_token()
    resp = client.post(
        f"/review/{batch.id}/confirm",
        data={
            "csrf_token": csrf,
            "candidate_ids": str(cand.id),
            "title": cand.title,
            "subject": cand.subject,
            "kind": cand.kind,
            "deadline": cand.deadline_date.isoformat(),
            "estimated_hours": str(cand.estimated_hours),
        },
    )
    assert resp.status_code == 303

    # Check Candidate updated
    db_session.refresh(cand)
    assert cand.status == "confirmed"

    # Check Task created
    tasks = db_session.query(Task).filter(Task.user_id == user.id).all()
    assert len(tasks) == 1
    t = tasks[0]
    assert t.title == "Web Dev Project"
    assert t.subject == "CS301"
    assert t.kind == "assignment"
    assert t.source == "extracted"
    assert t.candidate_id == cand.id
    assert t.deadline == date(2026, 10, 25)
    assert t.estimated_hours == 3.0

    # Check TaskHistory row created
    hist = db_session.query(TaskHistory).filter(TaskHistory.task_id == t.id).all()
    assert len(hist) == 1
    assert hist[0].event == "created"
    assert "extracted" in hist[0].new_value


def test_confirm_with_edited_date_and_hours(db_session):
    user = _create_user(db_session)
    batch, msgs = _create_batch_and_messages(db_session, user.id, count=1)
    cand = _create_candidate(
        db_session,
        user.id,
        msgs[0].id,
        title="Original Title",
        deadline_date=date(2026, 10, 20),
        estimated_hours=1.0,
    )

    client = _make_client(user.id, follow_redirects=False)

    csrf = generate_csrf_token()
    resp = client.post(
        f"/review/{batch.id}/confirm",
        data={
            "csrf_token": csrf,
            "candidate_ids": str(cand.id),
            "title": "Edited Title",
            "subject": "Math",
            "kind": "exam",
            "deadline": "2026-10-28",
            "estimated_hours": "5.5",
        },
    )
    assert resp.status_code == 303

    db_session.refresh(cand)
    assert cand.status == "confirmed"

    task = db_session.query(Task).filter(Task.user_id == user.id).first()
    assert task is not None
    assert task.title == "Edited Title"
    assert task.subject == "Math"
    assert task.kind == "exam"
    assert task.deadline == date(2026, 10, 28)
    assert task.estimated_hours == 5.5


def test_dismiss_candidate(db_session):
    user = _create_user(db_session)
    batch, msgs = _create_batch_and_messages(db_session, user.id, count=1)
    cand = _create_candidate(db_session, user.id, msgs[0].id, title="Irrelevant announcement")

    client = _make_client(user.id, follow_redirects=False)

    csrf = generate_csrf_token()
    resp = client.post(
        f"/review/{batch.id}/dismiss",
        data={"csrf_token": csrf, "candidate_ids": str(cand.id)},
    )
    assert resp.status_code == 303

    db_session.refresh(cand)
    assert cand.status == "dismissed"

    # Ensure no task created
    tasks = db_session.query(Task).filter(Task.user_id == user.id).all()
    assert len(tasks) == 0


def test_duplicate_group_creates_exactly_one_task(db_session):
    user = _create_user(db_session)
    batch, msgs = _create_batch_and_messages(db_session, user.id, count=2)

    # Two messages talking about the same assignment on the same date with slight punctuation / spacing difference
    c1 = _create_candidate(
        db_session,
        user.id,
        msgs[0].id,
        title="Submit Assignment 1",
        deadline_date=date(2026, 10, 22),
        quote="Submit assignment 1 by 22nd",
    )
    c2 = _create_candidate(
        db_session,
        user.id,
        msgs[1].id,
        title="submit  assignment 1.",
        deadline_date=date(2026, 10, 22),
        quote="Remember assignment 1 is due 22 Oct",
    )

    client = _make_client(user.id, follow_redirects=False)

    # Review page should merge them into 1 card with both quotes
    page_resp = client.get(f"/review/{batch.id}")
    assert page_resp.status_code == 200
    assert "Submit assignment 1 by 22nd" in page_resp.text
    assert "Remember assignment 1 is due 22 Oct" in page_resp.text
    assert "2 occurrences merged" in page_resp.text

    # Confirming the duplicate group
    csrf = generate_csrf_token()
    resp = client.post(
        f"/review/{batch.id}/confirm",
        data={
            "csrf_token": csrf,
            "candidate_ids": f"{c1.id},{c2.id}",
            "title": "Submit Assignment 1",
            "deadline": "2026-10-22",
            "estimated_hours": "2.0",
        },
    )
    assert resp.status_code == 303

    # Exactly ONE task created
    tasks = db_session.query(Task).filter(Task.user_id == user.id).all()
    assert len(tasks) == 1
    assert tasks[0].title == "Submit Assignment 1"

    # Both candidates marked confirmed
    db_session.refresh(c1)
    db_session.refresh(c2)
    assert c1.status == "confirmed"
    assert c2.status == "confirmed"


def test_same_title_with_different_dates_not_merged(db_session):
    user = _create_user(db_session)
    batch, msgs = _create_batch_and_messages(db_session, user.id, count=2)

    c1 = _create_candidate(
        db_session,
        user.id,
        msgs[0].id,
        title="Math Quiz",
        deadline_date=date(2026, 10, 15),
        quote="Quiz 1 on 15 Oct",
    )
    c2 = _create_candidate(
        db_session,
        user.id,
        msgs[1].id,
        title="Math Quiz",
        deadline_date=date(2026, 10, 22),
        quote="Quiz 2 on 22 Oct",
    )

    pending = candidate_service.get_pending_candidates_for_batch(db_session, user.id, batch.id)
    groups = candidate_service.group_candidates(pending)

    # Must NOT be merged: 2 distinct groups
    assert len(groups) == 2
    assert groups[0]["deadline_date"] != groups[1]["deadline_date"]
    # Both share the same normalized title and appear next to each other
    assert groups[0]["normalized_title"] == groups[1]["normalized_title"]


def test_bulk_confirm_skips_ambiguous_unresolved_probable_unclear(db_session):
    user = _create_user(db_session)
    batch, msgs = _create_batch_and_messages(db_session, user.id, count=5)

    # 1. Definite + ok -> MUST be confirmed
    c1 = _create_candidate(
        db_session,
        user.id,
        msgs[0].id,
        title="Definite Ok Task",
        certainty="definite",
        deadline_flag="ok",
        deadline_date=date(2026, 10, 20),
    )
    # 2. Probable + ok -> must NOT be confirmed
    c2 = _create_candidate(
        db_session,
        user.id,
        msgs[1].id,
        title="Probable Task",
        certainty="probable",
        deadline_flag="ok",
        deadline_date=date(2026, 10, 21),
    )
    # 3. Definite + ambiguous -> must NOT be confirmed
    c3 = _create_candidate(
        db_session,
        user.id,
        msgs[2].id,
        title="Ambiguous Task",
        certainty="definite",
        deadline_flag="ambiguous",
        deadline_date=date(2026, 10, 22),
    )
    # 4. Definite + unresolved -> must NOT be confirmed
    c4 = _create_candidate(
        db_session,
        user.id,
        msgs[3].id,
        title="Unresolved Task",
        certainty="definite",
        deadline_flag="unresolved",
        deadline_date=None,
    )
    # 5. Unclear + ok -> must NOT be confirmed
    c5 = _create_candidate(
        db_session,
        user.id,
        msgs[4].id,
        title="Unclear Task",
        certainty="unclear",
        deadline_flag="ok",
        deadline_date=date(2026, 10, 23),
    )

    client = _make_client(user.id, follow_redirects=True)

    csrf = generate_csrf_token()
    resp = client.post(
        f"/review/{batch.id}/confirm-definite",
        data={"csrf_token": csrf},
    )
    assert resp.status_code == 200
    assert "Confirmed 1 candidate(s)" in resp.text
    assert "4 left for manual review" in resp.text

    # Verify candidate statuses in DB
    db_session.refresh(c1)
    db_session.refresh(c2)
    db_session.refresh(c3)
    db_session.refresh(c4)
    db_session.refresh(c5)

    assert c1.status == "confirmed"
    assert c2.status == "pending"
    assert c3.status == "pending"
    assert c4.status == "pending"
    assert c5.status == "pending"

    # Only 1 task created
    tasks = db_session.query(Task).filter(Task.user_id == user.id).all()
    assert len(tasks) == 1
    assert tasks[0].title == "Definite Ok Task"


def test_user_b_cannot_access_user_a_batch_or_candidates(db_session):
    user_a = _create_user(db_session, email="usera@example.com")
    user_b = _create_user(db_session, email="userb@example.com")
    batch_a, msgs_a = _create_batch_and_messages(db_session, user_a.id, count=1)
    cand_a = _create_candidate(db_session, user_a.id, msgs_a[0].id, title="User A Task")

    client_b = _make_client(user_b.id, follow_redirects=False)

    # GET review page for User A's batch -> 404
    resp = client_b.get(f"/review/{batch_a.id}")
    assert resp.status_code == 404

    # POST confirm on User A's batch -> 404
    csrf = generate_csrf_token()
    resp = client_b.post(
        f"/review/{batch_a.id}/confirm",
        data={"csrf_token": csrf, "candidate_ids": str(cand_a.id), "title": "Hack"},
    )
    assert resp.status_code == 404

    # POST dismiss on User A's batch -> 404
    resp = client_b.post(
        f"/review/{batch_a.id}/dismiss",
        data={"csrf_token": csrf, "candidate_ids": str(cand_a.id)},
    )
    assert resp.status_code == 404

    # POST confirm-definite on User A's batch -> 404
    resp = client_b.post(
        f"/review/{batch_a.id}/confirm-definite",
        data={"csrf_token": csrf},
    )
    assert resp.status_code == 404

    # Ensure Candidate A is still pending and no task was created
    db_session.refresh(cand_a)
    assert cand_a.status == "pending"
    tasks_b = db_session.query(Task).filter(Task.user_id == user_b.id).all()
    assert len(tasks_b) == 0


def test_review_empty_state(db_session):
    user = _create_user(db_session)
    batch, msgs = _create_batch_and_messages(db_session, user.id, count=1)
    # No candidates created for this batch

    client = _make_client(user.id, follow_redirects=False)

    resp = client.get(f"/review/{batch.id}")
    assert resp.status_code == 200
    assert "Nothing to review. Import messages to get started." in resp.text
