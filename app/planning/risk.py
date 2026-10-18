"""
Risk Level calculation – Phase 8 Planning.

Pure, rule-based arithmetic. This is deterministic calculation, never machine learning.

Hand-calculated example:
-----------------------
Scenario 1:
- Task A: Overdue by 1 day (deadline was yesterday)
  -> risk_level(status='infeasible', days_left=-1, overdue=True) -> 'critical'

Scenario 2:
- Task B: Infeasible (slack < 0) and due tomorrow (days_left = 1 <= 2)
  -> risk_level(status='infeasible', days_left=1, overdue=False) -> 'critical'

Scenario 3:
- Task C: Infeasible (slack < 0) and due in 5 days (days_left = 5 > 2)
  -> risk_level(status='infeasible', days_left=5, overdue=False) -> 'high'

Scenario 4:
- Task D: Tight (0 <= slack < 0.2 * needed)
  -> risk_level(status='tight', days_left=4, overdue=False) -> 'moderate'

Scenario 5:
- Task E: Feasible (slack >= 0.2 * needed)
  -> risk_level(status='feasible', days_left=6, overdue=False) -> 'safe'

Scenario 6:
- Task F: Missing estimate or deadline
  -> risk_level(status=None, days_left=None, overdue=False) -> 'unknown'
"""


def risk_level(status: str | None = None, days_left: int | None = None, overdue: bool = False) -> str:
    """
    Pure, rule-based arithmetic assignment of risk category.
    Never uses machine learning.

    Returns:
    - 'critical' if overdue, or if infeasible with days_left <= 2
    - 'high' if infeasible (with days_left > 2 or days_left is None)
    - 'moderate' if tight
    - 'safe' if feasible
    - 'unknown' if status is missing, no estimate, or no deadline
    """
    if overdue:
        return "critical"

    if status == "infeasible":
        if days_left is not None and days_left <= 2:
            return "critical"
        return "high"

    if status == "tight":
        return "moderate"

    if status == "feasible":
        return "safe"

    return "unknown"
