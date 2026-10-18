"""
Phase 8 tests – Planning (Overrun factor, Feasibility, and Risk calculation).

Pure, rule-based arithmetic. All tests use fixed dates, never today's real date.
Never call any of this machine learning.

Hand-Calculated Example:
------------------------
Today: Monday 2026-10-12
Student Settings:
- Free hours per day: 3.0 hrs
- Free days: Mon, Tue, Wed, Thu, Fri (weekdays only)
- Overrun min samples: 5

Historical Completed Tasks:
1. est=2.0, act=3.0 -> ratio = 1.50
2. est=4.0, act=4.0 -> ratio = 1.00
3. est=1.0, act=2.0 -> ratio = 2.00
4. est=3.0, act=4.5 -> ratio = 1.50
5. est=2.0, act=2.5 -> ratio = 1.25
Ratios: [1.00, 1.25, 1.50, 1.50, 2.00] -> Median = 1.50.
So overrun_factor = 1.50.

Current Open Tasks:
Task A: Due Wednesday 2026-10-14, Estimated: 2.0 hrs
Task B: Due Monday 2026-10-19, Estimated: 6.0 hrs

Step 1: Task A (due Wednesday 2026-10-14)
- Calendar range: Mon 12, Tue 13, Wed 14 (3 days, all weekdays)
- available_A = 3 days * 3.0 hrs = 9.0 hrs
- needed_A = 2.0 hrs * 1.50 factor = 3.0 hrs
- slack_A = 9.0 - 3.0 = 6.0 hrs
- Threshold: 0.2 * 3.0 = 0.6 hrs
- slack_A (6.0) >= 0.6 -> status = 'feasible', risk = 'safe'

Step 2: Task B (due Monday 2026-10-19)
- Calendar range: Mon 12, Tue 13, Wed 14, Thu 15, Fri 16, Sat 17, Sun 18, Mon 19 (8 days)
  Weekdays: Mon, Tue, Wed, Thu, Fri, Mon (6 available days; Sat and Sun excluded)
- available_B = 6 days * 3.0 hrs = 18.0 hrs
- needed_B = needed_A + (6.0 hrs * 1.50) = 3.0 + 9.0 = 12.0 hrs (cumulative calculation)
- slack_B = 18.0 - 12.0 = 6.0 hrs
- Threshold: 0.2 * 12.0 = 2.4 hrs
- slack_B (6.0) >= 2.4 -> status = 'feasible', risk = 'safe'
"""

from datetime import date, datetime
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth.security import create_session_token, SESSION_COOKIE_NAME
from app.models import User, UserSettings, Task
from app.planning.overrun import overrun_factor, OverrunResult
from app.planning.feasibility import check_feasibility
from app.planning.risk import risk_level


class DummyTask:
    def __init__(self, id, title, status="pending", deadline=None, estimated_hours=None, actual_hours=None):
        self.id = id
        self.title = title
        self.status = status
        self.deadline = deadline
        self.estimated_hours = estimated_hours
        self.actual_hours = actual_hours


# ── 1. Overrun Tests ─────────────────────────────────────────────────

def test_overrun_below_min_samples_returns_default_and_insufficient_flag():
    # Only 3 completed tasks with estimates, below default min_samples (5)
    tasks = [
        DummyTask(1, "T1", status="completed", estimated_hours=2.0, actual_hours=3.0),
        DummyTask(2, "T2", status="completed", estimated_hours=4.0, actual_hours=6.0),
        DummyTask(3, "T3", status="completed", estimated_hours=1.0, actual_hours=2.0),
        DummyTask(4, "T4", status="pending", estimated_hours=2.0, actual_hours=None),  # open, ignored
    ]

    factor, n, insufficient_data = overrun_factor(tasks, min_samples=5)
    assert factor == 1.0
    assert n == 3
    assert insufficient_data is True


def test_overrun_with_enough_samples_returns_correct_median():
    # 5 completed tasks with actual/estimated ratios:
    # 2/2=1.0, 3/2=1.5, 4/2=2.0, 2/1=2.0, 3/1=3.0 -> Ratios: [1.0, 1.5, 2.0, 2.0, 3.0]
    tasks = [
        DummyTask(1, "T1", status="completed", estimated_hours=2.0, actual_hours=2.0),
        DummyTask(2, "T2", status="completed", estimated_hours=2.0, actual_hours=3.0),
        DummyTask(3, "T3", status="completed", estimated_hours=2.0, actual_hours=4.0),
        DummyTask(4, "T4", status="completed", estimated_hours=1.0, actual_hours=2.0),
        DummyTask(5, "T5", status="completed", estimated_hours=1.0, actual_hours=3.0),
    ]

    res = overrun_factor(tasks, min_samples=5)
    assert res.factor == 2.0
    assert res.n == 5
    assert res.insufficient_data is False


# ── 2. Feasibility Statuses: Feasible, Tight, Infeasible ──────────────

def test_feasibility_feasible_case():
    today = date(2026, 10, 12)  # Monday
    # Due Tuesday 2026-10-13 (2 days: Mon, Tue -> available = 8.0 hrs)
    # Estimate = 4.0 hrs, factor = 1.0 -> needed = 4.0 hrs
    # slack = 8.0 - 4.0 = 4.0 hrs. 4.0 >= 0.2 * 4.0 (0.8) -> feasible
    tasks = [
        DummyTask(1, "Assignment 1", status="pending", deadline=date(2026, 10, 13), estimated_hours=4.0)
    ]
    res = check_feasibility(tasks, today=today, free_hours_per_day=4.0, free_days="Mon,Tue,Wed,Thu,Fri,Sat,Sun", factor=1.0)
    assert len(res.tasks) == 1
    t = res.tasks[0]
    assert t["status"] == "feasible"
    assert t["needed"] == 4.0
    assert t["available"] == 8.0
    assert t["slack"] == 4.0
    assert "You need about 4.0 hours for tasks due by Tuesday and have about 8.0 available." in t["sentence"]


def test_feasibility_tight_case():
    today = date(2026, 10, 12)  # Monday
    # Due Tuesday 2026-10-13 (2 days -> available = 8.0 hrs)
    # Estimate = 7.0 hrs -> needed = 7.0 hrs. slack = 8.0 - 7.0 = 1.0 hr.
    # 0 <= slack (1.0) < 0.2 * needed (1.4) -> tight
    tasks = [
        DummyTask(1, "Big Essay", status="pending", deadline=date(2026, 10, 13), estimated_hours=7.0)
    ]
    res = check_feasibility(tasks, today=today, free_hours_per_day=4.0, factor=1.0)
    assert res.tasks[0]["status"] == "tight"
    assert res.tasks[0]["slack"] == 1.0


def test_feasibility_infeasible_case():
    today = date(2026, 10, 12)  # Monday
    # Due Tuesday 2026-10-13 (available = 8.0 hrs)
    # Estimate = 10.0 hrs -> needed = 10.0 hrs. slack = 8.0 - 10.0 = -2.0 hrs < 0 -> infeasible
    tasks = [
        DummyTask(1, "Giant Project", status="pending", deadline=date(2026, 10, 13), estimated_hours=10.0)
    ]
    res = check_feasibility(tasks, today=today, free_hours_per_day=4.0, factor=1.0)
    assert res.tasks[0]["status"] == "infeasible"
    assert res.tasks[0]["slack"] == -2.0
    # Also verify suggestion generated for overloaded workload
    assert len(res.suggestions) > 0
    assert "Giant Project" in res.suggestions[0]


# ── 3. Cumulative Calculation Across Two Deadlines ───────────────────

def test_two_tasks_with_different_deadlines_cumulative():
    today = date(2026, 10, 12)  # Monday
    # Task A: Due Wednesday 2026-10-14 (3 days: Mon, Tue, Wed = 9.0 available hrs), est = 4.0
    # Task B: Due Friday 2026-10-16 (5 days: Mon-Fri = 15.0 available hrs), est = 5.0
    # Cumulative:
    # Task A needed = 4.0 hrs
    # Task B needed = 4.0 + 5.0 = 9.0 hrs
    tasks = [
        DummyTask(2, "Task B", status="pending", deadline=date(2026, 10, 16), estimated_hours=5.0),
        DummyTask(1, "Task A", status="pending", deadline=date(2026, 10, 14), estimated_hours=4.0),
    ]

    res = check_feasibility(tasks, today=today, free_hours_per_day=3.0, factor=1.0)
    assert len(res.tasks) == 2

    # Should be sorted earliest deadline first: Task A then Task B
    item_a = res.tasks[0]
    item_b = res.tasks[1]
    assert item_a["task"].id == 1
    assert item_b["task"].id == 2

    assert item_a["needed"] == 4.0
    assert item_a["available"] == 9.0
    assert item_a["slack"] == 5.0

    assert item_b["needed"] == 9.0  # 4.0 + 5.0 cumulative
    assert item_b["available"] == 15.0
    assert item_b["slack"] == 6.0


# ── 4. Exclusions: No Estimate, No Deadline, Overdue ─────────────────

def test_task_with_no_estimate_excluded():
    today = date(2026, 10, 12)
    tasks = [
        DummyTask(1, "No Est Task", status="pending", deadline=date(2026, 10, 15), estimated_hours=None),
        DummyTask(2, "Zero Est Task", status="pending", deadline=date(2026, 10, 15), estimated_hours=0),
    ]
    res = check_feasibility(tasks, today=today)
    assert len(res.tasks) == 0
    assert len(res.no_estimate) == 2


def test_task_with_no_deadline_excluded():
    today = date(2026, 10, 12)
    tasks = [
        DummyTask(1, "Someday Task", status="pending", deadline=None, estimated_hours=3.0)
    ]
    res = check_feasibility(tasks, today=today)
    assert len(res.tasks) == 0
    assert len(res.no_deadline) == 1


def test_overdue_task_excluded_and_listed():
    today = date(2026, 10, 12)
    tasks = [
        DummyTask(1, "Old Task", status="pending", deadline=date(2026, 10, 10), estimated_hours=3.0)
    ]
    res = check_feasibility(tasks, today=today)
    assert len(res.tasks) == 0
    assert len(res.overdue) == 1
    assert res.overdue[0].title == "Old Task"


# ── 5. Free Days Filtering & Today Simplification ─────────────────────

def test_free_days_excluding_weekends_reduces_available_hours():
    today = date(2026, 10, 12)  # Monday
    # Deadline Sunday 2026-10-18 (7 calendar days)
    # Mon-Fri: 5 days. Sat-Sun excluded.
    # 5 days * 2.0 hrs/day = 10.0 hrs available (not 14.0)
    tasks = [
        DummyTask(1, "Weekend Free Test", status="pending", deadline=date(2026, 10, 18), estimated_hours=5.0)
    ]
    res = check_feasibility(tasks, today=today, free_hours_per_day=2.0, free_days="Mon,Tue,Wed,Thu,Fri", factor=1.0)
    assert res.tasks[0]["available"] == 10.0


def test_today_counts_as_full_day():
    today = date(2026, 10, 12)  # Monday
    # Due today (Mon 12 through Mon 12 inclusive = 1 day)
    tasks = [
        DummyTask(1, "Due Today", status="pending", deadline=date(2026, 10, 12), estimated_hours=2.0)
    ]
    res = check_feasibility(tasks, today=today, free_hours_per_day=3.0, factor=1.0)
    # 1 full day available = 3.0 hrs
    assert res.tasks[0]["available"] == 3.0


# ── 6. Risk Level for Every Branch ───────────────────────────────────

def test_risk_level_branches():
    # 1. Overdue -> critical
    assert risk_level(overdue=True) == "critical"
    assert risk_level(status="infeasible", days_left=5, overdue=True) == "critical"

    # 2. Infeasible with days_left <= 2 -> critical
    assert risk_level(status="infeasible", days_left=0, overdue=False) == "critical"
    assert risk_level(status="infeasible", days_left=1, overdue=False) == "critical"
    assert risk_level(status="infeasible", days_left=2, overdue=False) == "critical"

    # 3. Infeasible with days_left > 2 -> high
    assert risk_level(status="infeasible", days_left=3, overdue=False) == "high"
    assert risk_level(status="infeasible", days_left=7, overdue=False) == "high"
    assert risk_level(status="infeasible", days_left=None, overdue=False) == "high"

    # 4. Tight -> moderate
    assert risk_level(status="tight", days_left=1, overdue=False) == "moderate"
    assert risk_level(status="tight", days_left=5, overdue=False) == "moderate"

    # 5. Feasible -> safe
    assert risk_level(status="feasible", days_left=1, overdue=False) == "safe"
    assert risk_level(status="feasible", days_left=10, overdue=False) == "safe"

    # 6. Unknown / missing
    assert risk_level(status="unknown") == "unknown"
    assert risk_level(status=None) == "unknown"
    assert risk_level(status="no_estimate") == "unknown"
    assert risk_level(status="no_deadline") == "unknown"


# ── 7. UI Integration Test on /tasks ─────────────────────────────────

def test_tasks_page_renders_risk_badge_and_overrun(db_session):
    import uuid
    user = User(email=f"plan-{uuid.uuid4().hex[:6]}@test.com", password_hash="hash", display_name="Planner")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    settings = UserSettings(user_id=user.id, free_hours_per_day=3.0, overrun_min_samples=5)
    db_session.add(settings)

    # 1 open task
    t_open = Task(
        user_id=user.id,
        title="Feasible Term Paper",
        status="pending",
        deadline=date.today(),
        estimated_hours=1.0,
        source="manual",
    )
    db_session.add(t_open)
    db_session.commit()

    client = TestClient(app)
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    resp = client.get("/tasks")
    assert resp.status_code == 200
    # Overrun banner (insufficient samples)
    assert "Not enough data yet" in resp.text
    # Risk badge text
    assert "Risk:" in resp.text
    assert "You need about" in resp.text
