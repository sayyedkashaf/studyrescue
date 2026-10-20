import csv
import os
import sys
from unittest.mock import patch

from eval.metrics import prf
from eval.run_eval import load_labeled, score, main


def test_prf():
    result = prf(8, 2, 4)
    assert round(result["precision"], 4) == 0.8
    assert round(result["recall"], 4) == 0.6667
    assert round(result["f1"], 4) == 0.7273


def test_load_labeled(tmp_path):
    p = tmp_path / "data.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["message_id", "text", "sent_at", "gold_label", "split"])
        w.writerow(["1", "a", "", "commitment", "dev"])
        w.writerow(["2", "b", "", "", "dev"])
        w.writerow(["3", "c", "", "other", "test"])
    rows = load_labeled(str(p), "dev")
    assert len(rows) == 1
    assert rows[0]["message_id"] == "1"


def test_score():
    rows = [
        {"message_id": "1", "gold_label": "commitment"},
        {"message_id": "2", "gold_label": "commitment"},
        {"message_id": "3", "gold_label": "other"},
        {"message_id": "4", "gold_label": "other"},
        {"message_id": "5", "gold_label": "commitment"},
        {"message_id": "6", "gold_label": "other"},
    ]
    preds = {"1": True, "2": False, "3": True, "4": False, "5": False, "6": False}
    res = score(rows, preds)
    assert res["tp"] == 1
    assert res["fp"] == 1
    assert res["fn"] == 2
    assert res["tn"] == 2


def test_main_refuses_test_without_final(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    os.makedirs("eval/reports", exist_ok=True)
    monkeypatch.setattr(sys, "argv", ["run_eval", "--split", "test"])
    main()
    assert not os.path.exists("eval/reports/report_test.md")

from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import create_session_token, SESSION_COOKIE_NAME


def test_evaluation_page_logged_in_empty(db_session):
    from tests.test_phase6_extraction import _create_user
    user = _create_user(db_session)
    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    resp = client.get("/evaluation")
    assert resp.status_code == 200
    assert "No evaluation report yet. Run eval/run_eval.py." in resp.text


def test_evaluation_page_logged_out():
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/evaluation")
    assert resp.status_code in (302, 303, 307)
    assert "/auth/login" in resp.headers.get("location", "")
