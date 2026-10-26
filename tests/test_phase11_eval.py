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
    from eval.run_eval import main
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
    assert "No evaluation report yet" in resp.text


def test_evaluation_page_logged_out():
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/evaluation")
    assert resp.status_code in (302, 303, 307)
    assert "/auth/login" in resp.headers.get("location", "")

import tempfile
import os
from eval.make_label_sheet import build_sheet


def test_build_sheet_split_deterministic():
    txt = "12/10/26, 4:15 pm - A: hello\n12/10/26, 4:16 pm - A: world\n"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "chat.txt")
        with open(p, "w") as f:
            f.write(txt)
        c1 = os.path.join(d, "a.csv")
        c2 = os.path.join(d, "b.csv")
        build_sheet(p, c1)
        build_sheet(p, c2)
        assert open(c1).read() == open(c2).read()

import csv
import tempfile
import os
from eval.make_label_sheet import build_sheet


def test_build_sheet_split_by_date_no_cross_split():
    txt = "12/10/26, 4:15 pm - A: hello\n12/10/26, 4:16 pm - A: world\n13/10/26, 4:15 pm - A: test\n"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "chat.txt")
        with open(p, "w") as f:
            f.write(txt)
        c = os.path.join(d, "a.csv")
        build_sheet(p, c)
        with open(c) as f:
            rows = list(csv.DictReader(f))
        splits = {}
        for r in rows:
            dkey = r["sent_at"][:10]
            if dkey not in splits:
                splits[dkey] = set()
            splits[dkey].add(r["split"])
        for sset in splits.values():
            assert len(sset) == 1

import csv
import os
import tempfile
from eval.baselines import keyword_baseline_predict, evaluate_keyword, evaluate_tfidf_logreg


def test_keyword_baseline():
    assert keyword_baseline_predict("Submit assignment by tomorrow")


def test_baselines_use_splits(tmp_path):
    p = tmp_path / "labeled_messages.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["message_id", "text", "sent_at", "gold_label", "gold_kind", "gold_deadline_text", "gold_deadline_date", "split"])
        w.writerow(["1", "Submit assignment", "", "commitment", "", "", "", "dev"])
        w.writerow(["2", "hello there", "", "none", "", "", "", "test"])
    preds_k, test = evaluate_keyword(str(p))
    assert "2" in preds_k
    preds_t, test2 = evaluate_tfidf_logreg(str(p))
    assert "2" in preds_t

import os
import csv
import tempfile
from unittest.mock import patch

from eval.run_eval import gemini_predict, confusion, prf_from_cm, bootstrap_ci


def test_bootstrap_ci():
    y_true = [1,0,1,1,0]
    y_pred = [1,0,1,0,0]
    low, high = bootstrap_ci(y_true, y_pred, "f1", n=100, seed=1)
    assert 0 <= low <= high <= 1


def test_gemini_cached():
    with tempfile.TemporaryDirectory() as d:
        rows = [{"message_id": "1", "text": "Submit homework", "sent_at": "2026-01-01T00:00:00"}]
        with patch("eval.run_eval.extract_from_messages", return_value=[{"is_joke_or_hypothetical": False}]) as m:
            p1 = gemini_predict(rows, cache_dir=d)
            p2 = gemini_predict(rows, cache_dir=d)
            assert p1 == p2
            assert m.call_count == 1
