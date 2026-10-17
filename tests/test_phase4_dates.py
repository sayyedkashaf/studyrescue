"""
Phase 4 tests – Pure, deterministic date resolver test suite.

Table-driven pytest testing at least 40 cases covering:
- English and Hinglish relative days
- Weekdays (full, short, Hinglish)
- 'next <weekday>' and bare 'next week' / 'agle hafte'
- Day-first explicit dates (numeric and written)
- Weekday combined with explicit date
- Month boundaries, year boundaries, leap day
- Same weekday as reference date
- Time stripping
- Invalid dates returning (None, 'unresolved') without crashing
"""

from datetime import date, datetime
import pytest

from app.dates.resolver import resolve_deadline


# ── Table-Driven Test Cases ──────────────────────────────────────────

DATE_TEST_CASES = [
    # ── Cases from Prompt Specification ──────────────────────────────
    ("Friday 9th Oct", datetime(2026, 10, 5, 11, 20), date(2026, 10, 9), "ok"),
    ("next Wednesday", datetime(2026, 10, 6, 8, 55), date(2026, 10, 14), "ambiguous"),
    ("14th Oct", datetime(2026, 10, 6, 14, 0), date(2026, 10, 14), "ok"),
    ("kal", datetime(2026, 10, 6, 18, 30), date(2026, 10, 7), "ambiguous"),
    ("Sunday night", datetime(2026, 10, 6, 21, 0), date(2026, 10, 11), "ok"),
    ("tomorrow", datetime(2026, 10, 8, 9, 15), date(2026, 10, 9), "ok"),
    ("Monday 12th Oct", datetime(2026, 10, 9, 10, 30), date(2026, 10, 12), "ok"),
    ("19th Oct", datetime(2026, 10, 10, 12, 0), date(2026, 10, 19), "ok"),
    ("today night", datetime(2026, 10, 11, 16, 45), date(2026, 10, 11), "ok"),
    ("day after tomorrow", datetime(2026, 10, 12, 9, 0), date(2026, 10, 14), "ok"),
    ("aaj", datetime(2026, 10, 12, 11, 15), date(2026, 10, 12), "ok"),
    ("23rd October", datetime(2026, 10, 13, 14, 20), date(2026, 10, 23), "ok"),
    ("parso", datetime(2026, 10, 13, 17, 30), date(2026, 10, 15), "ok"),
    ("next Friday", datetime(2026, 10, 14, 10, 0), date(2026, 10, 23), "ambiguous"),
    ("Friday 23rd Oct", datetime(2026, 10, 15, 8, 30), date(2026, 10, 23), "ok"),
    ("Saturday 24th Oct", datetime(2026, 10, 15, 12, 45), date(2026, 10, 24), "ok"),
    ("next Monday", datetime(2026, 10, 16, 9, 0), date(2026, 10, 19), "ambiguous"),
    ("agle hafte tak", datetime(2026, 10, 16, 15, 0), date(2026, 10, 23), "ambiguous"),
    ("before next class", datetime(2026, 10, 9, 16, 0), None, "unresolved"),

    # ── Same Weekday as Reference Date ───────────────────────────────
    # Message sent on Friday saying 'Friday' -> same day
    ("Friday", datetime(2026, 10, 9, 10, 0), date(2026, 10, 9), "ok"),
    ("this Friday", datetime(2026, 10, 9, 14, 0), date(2026, 10, 9), "ok"),
    ("Monday", datetime(2026, 10, 5, 9, 0), date(2026, 10, 5), "ok"),
    ("this Monday", datetime(2026, 10, 5, 11, 0), date(2026, 10, 5), "ok"),

    # ── Month Boundaries ─────────────────────────────────────────────
    # Tomorrow from last day of October
    ("tomorrow", datetime(2026, 10, 31, 22, 0), date(2026, 11, 1), "ok"),
    # Day after tomorrow from last day of October
    ("day after tomorrow", datetime(2026, 10, 31, 18, 0), date(2026, 11, 2), "ok"),
    # Non-leap February end
    ("tomorrow", datetime(2026, 2, 28, 20, 0), date(2026, 3, 1), "ok"),

    # ── Year Boundaries ──────────────────────────────────────────────
    # Tomorrow on New Year's Eve
    ("tomorrow", datetime(2026, 12, 31, 23, 30), date(2027, 1, 1), "ok"),
    # Date mentioned in late December with month that already passed (January)
    ("15 Jan", datetime(2026, 12, 28, 10, 0), date(2027, 1, 15), "ok"),
    ("January 15", datetime(2026, 12, 28, 10, 0), date(2027, 1, 15), "ok"),
    ("15/01", datetime(2026, 12, 28, 10, 0), date(2027, 1, 15), "ok"),
    # Next week across year boundary
    ("next week", datetime(2026, 12, 30, 10, 0), date(2027, 1, 8), "ambiguous"),

    # ── Leap Day Cases ───────────────────────────────────────────────
    # 29 Feb in 2026 (not a leap year) must not crash, returns unresolved
    ("29 Feb", datetime(2026, 1, 10, 10, 0), None, "unresolved"),
    ("29/02/2026", datetime(2026, 1, 10, 10, 0), None, "unresolved"),
    # 29 Feb in 2028 (leap year) resolves correctly
    ("29 Feb 2028", datetime(2026, 1, 10, 10, 0), date(2028, 2, 29), "ok"),
    ("29/02/2028", datetime(2026, 1, 10, 10, 0), date(2028, 2, 29), "ok"),

    # ── Invalid Dates (Never throw exceptions) ───────────────────────
    ("31 Feb", datetime(2026, 1, 15, 10, 0), None, "unresolved"),
    ("32 Oct", datetime(2026, 10, 1, 10, 0), None, "unresolved"),
    ("31/04/2026", datetime(2026, 4, 1, 10, 0), None, "unresolved"),  # April has 30 days
    ("31/02", datetime(2026, 1, 1, 10, 0), None, "unresolved"),

    # ── Numeric Day-First Dates ──────────────────────────────────────
    ("12/10", datetime(2026, 10, 1, 10, 0), date(2026, 10, 12), "ok"),
    ("12/10/26", datetime(2026, 10, 1, 10, 0), date(2026, 10, 12), "ok"),
    ("12-10-2026", datetime(2026, 10, 1, 10, 0), date(2026, 10, 12), "ok"),
    ("05/11", datetime(2026, 10, 1, 10, 0), date(2026, 11, 5), "ok"),
    ("25-12", datetime(2026, 10, 1, 10, 0), date(2026, 12, 25), "ok"),

    # ── Hinglish Weekdays ────────────────────────────────────────────
    # Reference 2026-10-06 is Tuesday
    ("somvar", datetime(2026, 10, 6, 10, 0), date(2026, 10, 12), "ok"),
    ("mangalvar", datetime(2026, 10, 6, 10, 0), date(2026, 10, 6), "ok"),
    ("budhvar", datetime(2026, 10, 6, 10, 0), date(2026, 10, 7), "ok"),
    ("guruvar", datetime(2026, 10, 6, 10, 0), date(2026, 10, 8), "ok"),
    ("veervar", datetime(2026, 10, 6, 10, 0), date(2026, 10, 8), "ok"),
    ("shukravar", datetime(2026, 10, 6, 10, 0), date(2026, 10, 9), "ok"),
    ("shanivar", datetime(2026, 10, 6, 10, 0), date(2026, 10, 10), "ok"),
    ("ravivar", datetime(2026, 10, 6, 10, 0), date(2026, 10, 11), "ok"),

    # ── End of Week and EOD ──────────────────────────────────────────
    ("end of the week", datetime(2026, 10, 5, 9, 0), date(2026, 10, 9), "ok"),
    ("end of this week", datetime(2026, 10, 7, 12, 0), date(2026, 10, 9), "ok"),
    ("eod", datetime(2026, 10, 15, 14, 0), date(2026, 10, 15), "ok"),

    # ── Time Stripping and Prefixes ──────────────────────────────────
    ("Submit by Friday 9th Oct before 5 pm", datetime(2026, 10, 5, 11, 0), date(2026, 10, 9), "ok"),
    ("due by tomorrow 11:59 pm", datetime(2026, 10, 8, 14, 0), date(2026, 10, 9), "ok"),
    ("by 5 pm on Monday", datetime(2026, 10, 7, 10, 0), date(2026, 10, 12), "ok"),
    ("at 4:30 pm 18th Oct", datetime(2026, 10, 10, 9, 0), date(2026, 10, 18), "ok"),

    # ── Unresolved Vague Informal Phrases ────────────────────────────
    ("after next lab session", datetime(2026, 10, 5, 10, 0), None, "unresolved"),
    ("whenever sir gives", datetime(2026, 10, 5, 10, 0), None, "unresolved"),
    ("after diwali", datetime(2026, 10, 5, 10, 0), None, "unresolved"),
    ("", datetime(2026, 10, 5, 10, 0), None, "unresolved"),
    (None, datetime(2026, 10, 5, 10, 0), None, "unresolved"),
]


@pytest.mark.parametrize("deadline_text,reference,expected_date,expected_flag", DATE_TEST_CASES)
def test_resolve_deadline(deadline_text, reference, expected_date, expected_flag):
    res_date, res_flag = resolve_deadline(deadline_text, reference)
    assert res_date == expected_date, (
        f"Failed resolving '{deadline_text}' with ref {reference}. "
        f"Got {res_date}, expected {expected_date}."
    )
    assert res_flag == expected_flag, (
        f"Wrong flag for '{deadline_text}'. "
        f"Got '{res_flag}', expected '{expected_flag}'."
    )


def test_date_test_suite_size():
    """Ensure we have at least 40 test cases as required by the specification."""
    assert len(DATE_TEST_CASES) >= 40, f"Expected >= 40 test cases, found {len(DATE_TEST_CASES)}"
