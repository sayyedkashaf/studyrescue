"""
Feasibility calculation – Phase 8 Planning.

Pure, rule-based arithmetic. This is deterministic calculation, never machine learning.

Simplification:
- Today counts as a full day when summing available free hours from today through the deadline.

Hand-calculated example:
-----------------------
Reference date (today): Monday 2026-10-12
Free hours per day: 3.0
Free days: All 7 days (Mon-Sun)
Overrun factor: 1.0

Task 1: Due Tuesday 2026-10-13, Estimated: 5.0 hours
Task 2: Due Thursday 2026-10-15, Estimated: 4.0 hours

Calculation for Task 1 (due Tuesday):
- Days from Mon through Tue inclusive: Mon, Tue = 2 days
- available_1 = 2 days * 3.0 hrs/day = 6.0 hrs
- needed_1 = 5.0 hrs * 1.0 = 5.0 hrs
- slack_1 = 6.0 - 5.0 = 1.0 hr
- 0.2 * needed_1 = 1.0 hr
- Since slack_1 is not < 0, but slack_1 < 0.2 * needed_1 is False (1.0 == 1.0), status is 'feasible'.
  (If estimated was 5.5 hrs, needed=5.5, slack=0.5 < 1.1 -> status is 'tight'.)

Calculation for Task 2 (due Thursday):
- Days from Mon through Thu inclusive: Mon, Tue, Wed, Thu = 4 days
- available_2 = 4 days * 3.0 hrs/day = 12.0 hrs
- needed_2 = (5.0 + 4.0) * 1.0 = 9.0 hrs (cumulative workload)
- slack_2 = 12.0 - 9.0 = 3.0 hrs
- 0.2 * needed_2 = 1.8 hrs
- Since slack_2 (3.0) >= 1.8, status is 'feasible'.
"""

from datetime import date, timedelta
from typing import Sequence, Any, List, Dict, Set


class FeasibilityResult(dict):
    """
    Result dictionary that also supports attribute access.
    Pure, rule-based arithmetic output.
    """
    def __init__(self, tasks, no_estimate, no_deadline, overdue, suggestions=None):
        super().__init__(
            tasks=tasks,
            no_estimate=no_estimate,
            no_deadline=no_deadline,
            overdue=overdue,
            suggestions=suggestions or [],
        )
        self.tasks = tasks
        self.no_estimate = no_estimate
        self.no_deadline = no_deadline
        self.overdue = overdue
        self.suggestions = suggestions or []


def _parse_free_days(free_days: Any) -> Set[str]:
    """Normalizes free_days to a set of lowercase 3-letter abbreviations: {'mon', 'tue', ...}."""
    if not free_days:
        return {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    if isinstance(free_days, str):
        parts = [p.strip().lower() for p in free_days.split(",") if p.strip()]
    elif isinstance(free_days, (list, set, tuple)):
        parts = [str(p).strip().lower() for p in free_days]
    else:
        return {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}

    valid_abbrs = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    day_mapping = {
        "monday": "mon", "tuesday": "tue", "wednesday": "wed",
        "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
        "0": "mon", "1": "tue", "2": "wed", "3": "thu", "4": "fri", "5": "sat", "6": "sun"
    }

    normalized = set()
    for p in parts:
        abbr = p[:3]
        if abbr in valid_abbrs:
            normalized.add(abbr)
        elif p in day_mapping:
            normalized.add(day_mapping[p])

    return normalized if normalized else valid_abbrs


def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def check_feasibility(
    open_tasks: Sequence[Any],
    today: date,
    free_hours_per_day: float = 3.0,
    free_days: Any = "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
    factor: float = 1.0,
) -> FeasibilityResult:
    """
    Pure rule-based arithmetic check for task feasibility.
    Never uses machine learning.

    Parameters:
    - open_tasks: list of open tasks (pending or in_progress)
    - today: reference date (assumes full day available - simplification)
    - free_hours_per_day: study hours available per free day
    - free_days: weekdays student is available
    - factor: overrun multiplier from completed tasks

    Returns FeasibilityResult containing:
    - tasks: list of per-task evaluations with status, needed_i, available_i, slack_i, sentence
    - no_estimate: tasks lacking an estimate
    - no_deadline: tasks lacking a deadline
    - overdue: tasks with deadline before today
    - suggestions: advice on which tasks could move if overloaded
    """
    if free_hours_per_day is None or free_hours_per_day < 0:
        free_hours_per_day = 3.0
    if factor is None or factor <= 0:
        factor = 1.0

    allowed_days = _parse_free_days(free_days)

    no_estimate = []
    no_deadline = []
    overdue = []
    eligible = []

    for t in open_tasks:
        status = _get_field(t, "status", "pending")
        if status not in ("pending", "in_progress"):
            continue

        deadline = _get_field(t, "deadline")
        est_hours = _get_field(t, "estimated_hours")

        if deadline is None:
            no_deadline.append(t)
        elif deadline < today:
            overdue.append(t)
        elif est_hours is None or float(est_hours) <= 0:
            no_estimate.append(t)
        else:
            eligible.append(t)

    # Sort eligible tasks by deadline (earliest first)
    eligible.sort(key=lambda t: (_get_field(t, "deadline"), _get_field(t, "id", 0)))

    evaluated_tasks = []
    for t in eligible:
        deadline_i = _get_field(t, "deadline")

        # needed_i = sum(estimated_hours * factor) for all eligible tasks with deadline <= deadline_i
        needed_i = sum(
            float(_get_field(other, "estimated_hours")) * factor
            for other in eligible
            if _get_field(other, "deadline") <= deadline_i
        )

        # available_i = sum of free_hours_per_day for each date from today through deadline_i (inclusive)
        # Simplification: today counts as a full day.
        available_i = 0.0
        cur_date = today
        while cur_date <= deadline_i:
            if cur_date.strftime("%a").lower() in allowed_days:
                available_i += free_hours_per_day
            cur_date += timedelta(days=1)

        slack_i = available_i - needed_i

        # status_i = 'infeasible' if slack_i < 0, 'tight' if slack_i < 0.2 * needed_i, else 'feasible'.
        if slack_i < 0:
            status_i = "infeasible"
        elif slack_i < 0.2 * needed_i:
            status_i = "tight"
        else:
            status_i = "feasible"

        day_name = deadline_i.strftime("%A")
        sentence_i = (
            f"You need about {needed_i:.1f} hours for tasks due by {day_name} "
            f"and have about {available_i:.1f} available."
        )

        days_left = (deadline_i - today).days

        evaluated_tasks.append({
            "task": t,
            "task_id": _get_field(t, "id"),
            "status": status_i,
            "needed": needed_i,
            "available": available_i,
            "slack": slack_i,
            "days_left": days_left,
            "sentence": sentence_i,
        })

    # Suggestions if workload exceeds available time
    suggestions = []
    infeasible_tasks = [item for item in evaluated_tasks if item["status"] == "infeasible"]
    if infeasible_tasks:
        # Sort by latest deadline first, then lowest slack
        infeasible_sorted = sorted(
            infeasible_tasks,
            key=lambda item: (_get_field(item["task"], "deadline"), -item["slack"]),
            reverse=True,
        )
        task_names = [f"'{_get_field(item['task'], 'title')}'" for item in infeasible_sorted[:3]]
        suggestions.append(
            f"Workload exceeds available time. Consider moving or renegotiating tasks with late deadlines: "
            + ", ".join(task_names)
            + "."
        )

    return FeasibilityResult(
        tasks=evaluated_tasks,
        no_estimate=no_estimate,
        no_deadline=no_deadline,
        overdue=overdue,
        suggestions=suggestions,
    )
