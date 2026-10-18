"""
Overrun factor calculation – Phase 8 Planning.

Pure, rule-based arithmetic. This is deterministic calculation, never machine learning.
Computes a student's historical time estimation multiplier from completed tasks.
"""

from typing import NamedTuple, Sequence, Any
import statistics


class OverrunResult(NamedTuple):
    factor: float
    n: int
    insufficient_data: bool


def overrun_factor(tasks: Sequence[Any], min_samples: int = 5) -> OverrunResult:
    """
    Pure arithmetic calculation: takes completed tasks that have both
    estimated_hours and actual_hours (both > 0) and returns (factor, n, insufficient_data).

    factor = median(actual / estimated).
    If n < min_samples (default 5): returns (1.0, n, insufficient_data=True).
    Otherwise returns (factor, n, insufficient_data=False).

    Pure, rule-based arithmetic; never machine learning.
    """
    if min_samples is None:
        min_samples = 5

    ratios = []
    for t in tasks:
        status = getattr(t, "status", None) if not isinstance(t, dict) else t.get("status")
        if status == "completed":
            est = getattr(t, "estimated_hours", None) if not isinstance(t, dict) else t.get("estimated_hours")
            act = getattr(t, "actual_hours", None) if not isinstance(t, dict) else t.get("actual_hours")
            if est is not None and act is not None:
                try:
                    est_f = float(est)
                    act_f = float(act)
                    if est_f > 0 and act_f > 0:
                        ratios.append(act_f / est_f)
                except (ValueError, TypeError):
                    continue

    n = len(ratios)
    if n < min_samples:
        return OverrunResult(factor=1.0, n=n, insufficient_data=True)

    factor = float(statistics.median(ratios))
    return OverrunResult(factor=factor, n=n, insufficient_data=False)
