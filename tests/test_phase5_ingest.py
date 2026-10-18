"""
Phase 5 tests – Ingest.

Covers the WhatsApp export parser, the pasted-text splitter, the batch
service (with strict user isolation), and the /imports page (form,
validation, summary, listing, delete).
"""

import io
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import create_session_token, SESSION_COOKIE_NAME, hash_password, generate_csrf_token
from app.models import User, UserSettings, Message
from app.services import batch_service
from app.ingest.whatsapp_parser import parse_whatsapp_export
from app.ingest.text_splitter import split_pasted_text, is_whatsapp_format

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEMO_CHAT = FIXTURES / "demo_chat_SYNTHETIC.txt"


def _create_user(db, email="u@example.com", display_name="User"):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return existing
    user = User(email=email, password_hash=hash_password("Password123"), display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    settings = UserSettings(user_id=user.id)
    db.add(settings)
    db.commit()
    return user


def _login(db, email="u@example.com", display_name="User"):
    user = _create_user(db, email=email, display_name=display_name)
    token = create_session_token(user.id)
    client = TestClient(app, follow_redirects=False)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    return client, user

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEMO_CHAT = FIXTURES / "demo_chat_SYNTHETIC.txt"


# ── WhatsApp parser tests ──────────────────────────────────────────────

def test_parser_android_12_hour():
    msgs = parse_whatsapp_export("05/10/26, 9:05 am - Neha (CR): Good morning everyone.")
    assert len(msgs) == 1
    assert msgs[0].sent_at == datetime(2026, 10, 5, 9, 5)
    assert msgs[0].sender_alias == "Sender 1"
    assert msgs[0].text == "Good morning everyone."
    assert msgs[0].line_no == 1


def test_parser_ios_with_seconds():
    msgs = parse_whatsapp_export("[12/10/26, 4:15:30 PM] Riya: hello there")
    assert len(msgs) == 1
    assert msgs[0].sent_at == datetime(2026, 10, 12, 16, 15, 30)
    assert msgs[0].sender_alias == "Sender 1"
    assert msgs[0].text == "hello there"


def test_parser_24_hour_time():
    msgs = parse_whatsapp_export("12/10/26, 16:15 - Dev: hello")
    assert len(msgs) == 1
    assert msgs[0].sent_at == datetime(2026, 10, 12, 16, 15)
    assert msgs[0].sender_alias == "Sender 1"


def test_parser_four_digit_year():
    msgs = parse_whatsapp_export("12/10/2026, 9:00 am - Neha: hi")
    assert len(msgs) == 1
    assert msgs[0].sent_at == datetime(2026, 10, 12, 9, 0)


def test_parser_multi_line_joined():
    text = (
        "06/10/26, 7:45 pm - Riya: Reminder for everyone:\n"
        "Mini project topic selection form has to be filled\n"
        "by Sunday night. Pls don't forget"
    )
    msgs = parse_whatsapp_export(text)
    assert len(msgs) == 1
    assert msgs[0].sent_at == datetime(2026, 10, 6, 19, 45)
    assert msgs[0].line_no == 1
    assert "Sunday night" in msgs[0].text
    assert msgs[0].text.count("\n") == 2


def test_parser_system_lines_skipped():
    text = (
        "05/10/26, 9:00 am - Messages and calls are end-to-end encrypted. No one outside of this chat can read them.\n"
        "05/10/26, 9:02 am - Neha (CR) created group \"DS Sem 5\"\n"
        "05/10/26, 9:05 am - Neha (CR): hello\n"
        "05/10/26, 2:10 pm - Dev: <Media omitted>\n"
        "07/10/26, 12:30 pm - Aman: This message was deleted\n"
        "08/10/26, 10:00 am - a random timestamped line with no sender\n"
    )
    msgs = parse_whatsapp_export(text)
    assert len(msgs) == 1
    assert msgs[0].sender_alias == "Sender 1"
    assert msgs[0].text == "hello"


def test_parser_anonymisation_stable_aliases():
    text = (
        "05/10/26, 9:05 am - Neha (CR): a\n"
        "05/10/26, 9:41 am - Aman: b\n"
        "05/10/26, 11:20 am - Neha (CR): c\n"
        "05/10/26, 2:10 pm - +91 98765 43210: d\n"
    )
    msgs = parse_whatsapp_export(text)
    assert [m.sender_alias for m in msgs] == ["Sender 1", "Sender 2", "Sender 1", "Sender 3"]
    joined = " ".join(m.sender_alias for m in msgs)
    assert "Neha" not in joined
    assert "Aman" not in joined
    assert "98765" not in joined


def test_parser_phone_number_gets_alias():
    msgs = parse_whatsapp_export("05/10/26, 9:05 am - +1-555-000-1234: hi")
    assert len(msgs) == 1
    assert msgs[0].sender_alias == "Sender 1"


def test_parser_bom_and_windows_line_endings():
    text = "\ufeff05/10/26, 9:05 am - Neha: a\r\n05/10/26, 9:41 am - Aman: b\r\n"
    msgs = parse_whatsapp_export(text)
    assert len(msgs) == 2
    assert msgs[0].sender_alias == "Sender 1"
    assert msgs[1].sender_alias == "Sender 2"


def test_parser_empty_input_returns_empty_list():
    assert parse_whatsapp_export("") == []
    assert parse_whatsapp_export("   \n  ") == []
    assert parse_whatsapp_export(None) == []


def test_demo_file_numbers():
    """The demo file has 48 timestamped lines; 5 are system/media/deleted."""
    text = DEMO_CHAT.read_text(encoding="utf-8")
    msgs = parse_whatsapp_export(text)
    assert len(msgs) == 43, f"expected 43 messages, got {len(msgs)}"
    assert len({m.sender_alias for m in msgs}) == 6

    riya = [m for m in msgs if "Sunday night" in m.text]
    assert len(riya) == 1
    assert riya[0].sent_at == datetime(2026, 10, 6, 19, 45)
    assert riya[0].line_no == 16


# ── Text splitter tests ────────────────────────────────────────────────

def test_splitter_plain_text_with_reference_date():
    ref = datetime(2026, 10, 15, 12, 0, 0)
    msgs = split_pasted_text("First message here.\n\nSecond message here.", ref)
    assert len(msgs) == 2
    assert msgs[0].text == "First message here."
    assert msgs[1].text == "Second message here."
    assert all(m.sent_at == ref for m in msgs)
    assert all(m.sender_alias == "Sender 1" for m in msgs)


def test_splitter_defaults_to_now():
    msgs = split_pasted_text("Solo message.")
    assert len(msgs) == 1
    assert msgs[0].sent_at is not None
    assert abs((datetime.now() - msgs[0].sent_at).total_seconds()) < 60


def test_splitter_whatsapp_paste_delegates_to_parser():
    text = DEMO_CHAT.read_text(encoding="utf-8")
    msgs = split_pasted_text(text)
    assert len(msgs) == 43


def test_is_whatsapp_format_detection():
    assert is_whatsapp_format("12/10/26, 4:15 pm - Name: message") is True
    assert is_whatsapp_format("[12/10/26, 4:15:30 PM] Name: message") is True
    assert is_whatsapp_format("Just some random plain text.") is False
    assert is_whatsapp_format("") is False


# ── Batch service tests ────────────────────────────────────────────────

def _sample_messages():
    return parse_whatsapp_export("05/10/26, 9:05 am - Neha: a\n05/10/26, 9:41 am - Aman: b\n")


def test_batch_service_create_list_get_filters_by_user(db_session, user_a, user_b):
    msgs = _sample_messages()
    batch = batch_service.create_batch(db_session, user_a.id, "WhatsApp.txt", msgs)
    assert batch.id is not None
    assert batch.user_id == user_a.id
    assert batch.message_count == 2

    assert len(batch_service.list_batches(db_session, user_a.id)) == 1
    assert batch_service.list_batches(db_session, user_b.id) == []

    got = batch_service.get_batch(db_session, user_a.id, batch.id)
    assert got is not None and got.message_count == 2

    # User B cannot see or delete user A's batch
    assert batch_service.get_batch(db_session, user_b.id, batch.id) is None
    assert batch_service.delete_batch(db_session, user_b.id, batch.id) is False

    # User A can delete it
    assert batch_service.delete_batch(db_session, user_a.id, batch.id) is True
    assert batch_service.get_batch(db_session, user_a.id, batch.id) is None


def test_batch_messages_stamp_user_id_and_aliases(db_session, user_a):
    msgs = _sample_messages()
    batch = batch_service.create_batch(db_session, user_a.id, "x.txt", msgs)
    rows = db_session.query(Message).filter(Message.batch_id == batch.id).all()
    assert len(rows) == 2
    assert all(r.user_id == user_a.id for r in rows)
    assert rows[0].sender_alias == "Sender 1"
    assert rows[1].sender_alias == "Sender 2"
    assert all("Neha" not in (r.sender_alias or "") for r in rows)


# ── Import page tests ──────────────────────────────────────────────────

def test_imports_get_shows_form(db_session):
    client, _ = _login(db_session, email="form_student@university.ac.in")
    resp = client.get("/imports")
    assert resp.status_code == 200
    body = resp.text
    assert "Imports" in body
    assert 'id="paste-text"' in body
    assert 'name="upload_file"' in body
    assert 'id="reference-date"' in body
    assert 'name="csrf_token"' in body


def test_imports_get_empty_state(db_session):
    client, _ = _login(db_session, email="empty_student@university.ac.in")
    resp = client.get("/imports")
    assert resp.status_code == 200
    assert "No imports yet" in resp.text


def test_import_valid_paste_shows_summary(db_session):
    client, user = _login(db_session, email="importer@university.ac.in")
    text = (
        "05/10/26, 9:05 am - Neha (CR): Good morning everyone.\n"
        "05/10/26, 9:41 am - Aman: ok di\n"
        "06/10/26, 7:45 pm - Riya: Reminder for everyone:\nby Sunday night. Pls don't forget\n"
    )
    resp = client.post(
        "/imports",
        data={"paste_text": text, "reference_date": "", "csrf_token": generate_csrf_token()},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Import Summary" in body
    assert "3" in body  # message count
    assert "3" in body  # distinct sender count (Sender 1, Sender 2, Sender 3)
    assert "Sunday night" in body
    assert "05 Oct" in body and "06 Oct" in body  # date range

    batch = batch_service.list_batches(db_session, user.id)[0]
    assert batch.message_count == 3
    rows = db_session.query(Message).filter(Message.batch_id == batch.id).all()
    aliases = [r.sender_alias for r in rows]
    assert aliases == ["Sender 1", "Sender 2", "Sender 3"]
    assert all("Neha" not in (a or "") for a in aliases)
    assert all("Riya" not in (a or "") for a in aliases)
    riya_row = [r for r in rows if r.text and "Sunday night" in r.text][0]
    assert riya_row.sent_at == datetime(2026, 10, 6, 19, 45)


def test_import_plain_paste_uses_reference_date(db_session):
    client, user = _login(db_session, email="refdate_student@university.ac.in")
    resp = client.post(
        "/imports",
        data={
            "paste_text": "Hello world.\n\nSecond message.",
            "reference_date": "2026-10-15",
            "csrf_token": generate_csrf_token(),
        },
    )
    assert resp.status_code == 200
    batch = batch_service.list_batches(db_session, user.id)[0]
    rows = db_session.query(Message).filter(Message.batch_id == batch.id).all()
    assert len(rows) == 2
    assert all(r.sent_at == datetime(2026, 10, 15, 0, 0) for r in rows)


def test_import_rejects_empty_input(db_session):
    client, _ = _login(db_session, email="empty_input_student@university.ac.in")
    resp = client.post(
        "/imports",
        data={"paste_text": "", "reference_date": "", "csrf_token": generate_csrf_token()},
    )
    assert resp.status_code == 422
    assert "paste" in resp.text.lower()


def test_import_rejects_wrong_file_type(db_session):
    client, _ = _login(db_session, email="filetype_student@university.ac.in")
    resp = client.post(
        "/imports",
        data={"csrf_token": generate_csrf_token()},
        files={"upload_file": ("chat.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )
    assert resp.status_code == 422
    assert ".txt" in resp.text


def test_import_rejects_empty_file(db_session):
    client, _ = _login(db_session, email="emptyfile_student@university.ac.in")
    resp = client.post(
        "/imports",
        data={"csrf_token": generate_csrf_token()},
        files={"upload_file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert resp.status_code == 422
    assert "empty" in resp.text.lower()


def test_import_rejects_file_over_2mb(db_session):
    client, _ = _login(db_session, email="bigfile_student@university.ac.in")
    big = b"x" * (2 * 1024 * 1024 + 1)
    resp = client.post(
        "/imports",
        data={"csrf_token": generate_csrf_token()},
        files={"upload_file": ("big.txt", io.BytesIO(big), "text/plain")},
    )
    assert resp.status_code == 422
    assert "2 MB" in resp.text or "too large" in resp.text.lower()


def test_import_rejects_invalid_utf8(db_session):
    client, _ = _login(db_session, email="utf8_student@university.ac.in")
    resp = client.post(
        "/imports",
        data={"csrf_token": generate_csrf_token()},
        files={"upload_file": ("bad.txt", io.BytesIO(b"\xff\xfe not utf-8"), "text/plain")},
    )
    assert resp.status_code == 422
    assert "UTF-8" in resp.text


def test_import_whatsapp_file(db_session):
    client, user = _login(db_session, email="fileimport_student@university.ac.in")
    content = DEMO_CHAT.read_bytes()
    resp = client.post(
        "/imports",
        data={"csrf_token": generate_csrf_token()},
        files={"upload_file": ("demo.txt", io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Import Summary" in body
    assert "43" in body   # message count from the demo file
    assert "6" in body    # distinct senders

    # Full verification lives in the database (preview only shows the first 10)
    batch = batch_service.list_batches(db_session, user.id)[0]
    assert batch.message_count == 43
    rows = db_session.query(Message).filter(Message.batch_id == batch.id).all()
    assert len(rows) == 43
    assert len({r.sender_alias for r in rows}) == 6
    riya_row = [r for r in rows if r.text and "Sunday night" in r.text][0]
    assert riya_row.sent_at == datetime(2026, 10, 6, 19, 45)
    assert riya_row.sender_alias == "Sender 5"   # 5th distinct sender in the demo
    assert riya_row.user_id == user.id
    assert all("Neha" not in (r.sender_alias or "") for r in rows)
    assert all("Riya" not in (r.sender_alias or "") for r in rows)


def test_delete_confirmation_page_own_batch(db_session):
    client, user = _login(db_session, email="delete_student@university.ac.in")
    msgs = _sample_messages()
    batch = batch_service.create_batch(db_session, user.id, "secret.txt", msgs)
    resp = client.get(f"/imports/{batch.id}/delete")
    assert resp.status_code == 200
    assert "Confirm Deletion" in resp.text
    assert "secret.txt" in resp.text
    assert 'name="csrf_token"' in resp.text


def test_user_b_cannot_view_or_delete_user_a_batch(db_session):
    client_a, user_a = _login(db_session, email="iso_a@university.ac.in")
    client_b, user_b = _login(db_session, email="iso_b@university.ac.in")

    msgs = _sample_messages()
    batch = batch_service.create_batch(db_session, user_a.id, "secret.txt", msgs)

    # User B's imports page lists nothing from user A
    resp_b = client_b.get("/imports")
    assert resp_b.status_code == 200
    assert "secret.txt" not in resp_b.text

    # User B cannot open the deletion confirmation page (404)
    assert client_b.get(f"/imports/{batch.id}/delete").status_code == 404

    # User B cannot delete the batch (404); batch still exists for user A
    resp = client_b.post(f"/imports/{batch.id}/delete", data={"csrf_token": generate_csrf_token()})
    assert resp.status_code == 404
    assert batch_service.get_batch(db_session, user_a.id, batch.id) is not None

    # User A deletes it successfully
    resp = client_a.post(f"/imports/{batch.id}/delete", data={"csrf_token": generate_csrf_token()})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/imports"
    assert batch_service.get_batch(db_session, user_a.id, batch.id) is None


def test_delete_rejects_invalid_csrf(db_session):
    client, user = _login(db_session, email="csrf_student@university.ac.in")
    msgs = _sample_messages()
    batch = batch_service.create_batch(db_session, user.id, "secret.txt", msgs)
    resp = client.post(f"/imports/{batch.id}/delete", data={"csrf_token": "tampered-token"})
    assert resp.status_code == 400
    assert batch_service.get_batch(db_session, user.id, batch.id) is not None
