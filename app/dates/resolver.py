"""
Deterministic Date Resolver for Study Rescue.

Pure, deterministic rule-based logic resolving informal deadline texts into real dates
relative to a reference message timestamp.

The LLM never computes dates; this module handles all date resolution.
"""

from datetime import date, datetime, timedelta
import re

from app.dates.hinglish import WEEKDAYS, MONTHS, RELATIVE_DAYS


# ── Time and Filler Stripping Patterns ───────────────────────────────

# Matches times like '5 pm', '5:30 pm', '11:59pm', '17:00', '5pm', '5 baje', '5 baje tak', '5 tak'
_TIME_PATTERN = re.compile(
    r"\b(?:at|by|before)?\s*\d{1,2}(?::\d{2})?\s*(?:(?:am|pm|hrs?|hours?|baje|bje)(?:\s+tak)?|tak)\b",
    re.IGNORECASE,
)
_TIME_24H_PATTERN = re.compile(r"\b\d{1,2}:\d{2}\b")

# Filler words at beginning or end of phrases
_PREFIX_FILLERS = re.compile(
    r"^(?:submit\s+by|submission\s+by|due\s+on|due\s+by|before|by|on|till|around|tak)\s+",
    re.IGNORECASE,
)
_SUFFIX_FILLERS = re.compile(
    r"\s+(?:tak|sharp|morning|afternoon|evening|night|eod)$",
    re.IGNORECASE,
)


def _clean_text(raw_text: str) -> str:
    """Cleans time stamps, punctuation, and extraneous whitespace."""
    text = raw_text.strip().lower()

    # Preserve special compound relative phrases before stripping fillers
    if text in ("today night", "aaj raat", "tonight"):
        return "today"

    # Remove times: 'by 5 pm', 'before 11:59 pm', '5:30pm', etc.
    text = _TIME_PATTERN.sub(" ", text)
    text = _TIME_24H_PATTERN.sub(" ", text)

    # Normalize punctuation (keep / and - for dates)
    text = re.sub(r"[,;:\'\"!?()\[\]]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Repeatedly remove prefix fillers (e.g. 'by', 'on', 'submit by')
    while True:
        new_text = _PREFIX_FILLERS.sub("", text).strip()
        if new_text == text:
            break
        text = new_text

    # If it ends with night/morning/evening (e.g. 'Sunday night' -> 'Sunday')
    # but do NOT strip 'eod' if that's the entire text
    if text != "eod":
        text = _SUFFIX_FILLERS.sub("", text).strip()

    return text


def _safe_date(year: int, month: int, day: int) -> date | None:
    """Safely constructs a date object, returning None on invalid dates (e.g. 31 Feb)."""
    try:
        return date(year, month, day)
    except (ValueError, OverflowError):
        return None


def _nearest_future_date(ref_date: date, month: int, day: int, explicit_year: int | None = None) -> date | None:
    """
    Constructs a valid date. If year is omitted, picks the nearest occurrence
    on or after ref_date (this year, or next year if month/day has passed).
    """
    if explicit_year is not None:
        year = explicit_year
        if year < 100:
            year += 2000
        return _safe_date(year, month, day)

    # Missing year: evaluate in current reference year
    candidate = _safe_date(ref_date.year, month, day)
    if candidate is not None:
        if candidate >= ref_date:
            return candidate
        # If already passed in current year, advance to next year
        next_year_candidate = _safe_date(ref_date.year + 1, month, day)
        return next_year_candidate

    # If candidate failed (e.g. Feb 29 in non-leap year 2026), check next year (e.g. 2028 or leap year)
    candidate_next = _safe_date(ref_date.year + 1, month, day)
    return candidate_next


# ── Explicit Date Parsers ────────────────────────────────────────────

def _parse_explicit_date(cleaned: str, ref_date: date) -> tuple[date | None, str | None]:
    """
    Parses explicit day-first dates with day numbers, month names, or slashes/dashes:
    - 9th Oct, 14th Oct, 23rd October, 12 Oct 2026
    - October 12, Oct 9th
    - 12/10, 12/10/26, 12-10-2026
    Returns (resolved_date, 'ok') if matched and valid, or (None, None) if not an explicit date.
    """
    # 1. 'DDth Month [YYYY]' e.g. '9th Oct', '14th oct', 'Friday 9th Oct', '23rd October'
    m_day_month = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+)(?:\s+(\d{2,4}))?\b",
        cleaned,
    )
    if m_day_month:
        day_str, month_str, year_str = m_day_month.groups()
        month_key = month_str.lower()
        if month_key in MONTHS:
            month = MONTHS[month_key]
            day = int(day_str)
            year = int(year_str) if year_str else None
            d = _nearest_future_date(ref_date, month, day, year)
            if d is not None:
                return d, "ok"
            # Invalid date (e.g. 31 Feb)
            return None, "unresolved"

    # 2. 'Month DDth [YYYY]' e.g. 'October 12', 'Oct 9th 2026'
    m_month_day = re.search(
        r"\b([a-zA-Z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{2,4}))?\b",
        cleaned,
    )
    if m_month_day:
        month_str, day_str, year_str = m_month_day.groups()
        month_key = month_str.lower()
        if month_key in MONTHS:
            month = MONTHS[month_key]
            day = int(day_str)
            year = int(year_str) if year_str else None
            d = _nearest_future_date(ref_date, month, day, year)
            if d is not None:
                return d, "ok"
            return None, "unresolved"

    # 3. Numeric day-first: 'DD/MM/YYYY', 'DD/MM/YY', 'DD/MM' or 'DD-MM-YYYY', 'DD-MM'
    m_numeric = re.search(
        r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b",
        cleaned,
    )
    if m_numeric:
        day_str, month_str, year_str = m_numeric.groups()
        day = int(day_str)
        month = int(month_str)
        year = int(year_str) if year_str else None
        if 1 <= month <= 12 and 1 <= day <= 31:
            d = _nearest_future_date(ref_date, month, day, year)
            if d is not None:
                return d, "ok"
            return None, "unresolved"

    return None, None


# ── Main Resolver Function ───────────────────────────────────────────

def resolve_deadline(deadline_text: str | None, reference: datetime) -> tuple[date | None, str]:
    """
    Pure, deterministic date resolution.
    Takes a raw deadline string and a message reference datetime.
    Returns (date_or_none, flag) where flag is:
      - 'ok': unambiguously resolved
      - 'ambiguous': resolved to a best interpretation, but requires student confirmation
      - 'unresolved': unable to deterministically resolve, student must pick date manually
    Never throws exceptions.
    """
    if not deadline_text or not deadline_text.strip():
        return None, "unresolved"

    ref_date = reference.date()
    cleaned = _clean_text(deadline_text)

    if not cleaned:
        return None, "unresolved"

    # ── Rule 1: Explicit dates take precedence ───────────────────────
    # If a weekday and an explicit date both appear (e.g. 'Friday 9th Oct'),
    # the explicit date is trusted.
    explicit_date, explicit_flag = _parse_explicit_date(cleaned, ref_date)
    if explicit_flag is not None:
        return explicit_date, explicit_flag

    # ── Rule 2: Relative single-day keywords ─────────────────────────
    # Exact phrase matches for today, tomorrow, kal, parso, etc.
    for phrase, (offset, flag) in RELATIVE_DAYS.items():
        if cleaned == phrase or cleaned == f"this {phrase}":
            # Note on 'kal': In Hindi/Hinglish, 'kal' can mean either tomorrow
            # or yesterday depending on tense. It is resolved to tomorrow (+1 day)
            # but always flagged 'ambiguous'.
            return ref_date + timedelta(days=offset), flag

    # ── Rule 3: End of the week / EOD ────────────────────────────────
    # 'end of the week' means Friday.
    if cleaned in ("end of the week", "end of this week", "end of week"):
        ref_weekday = ref_date.weekday()
        if ref_weekday <= 4:
            days_ahead = 4 - ref_weekday
        else:
            days_ahead = (4 - ref_weekday) + 7
        return ref_date + timedelta(days=days_ahead), "ok"

    # ── Rule 4: Bare 'next week' / 'agle hafte' ──────────────────────
    # Resolves to the Friday of the following calendar week (weeks run Mon-Sun).
    # Always flagged 'ambiguous' because students use 'next week' without specifying a day.
    if cleaned in ("next week", "agle hafte", "agle hafte tak"):
        current_monday = ref_date - timedelta(days=ref_date.weekday())
        following_friday = current_monday + timedelta(days=7 + 4)
        return following_friday, "ambiguous"

    # ── Rule 5: 'next <weekday>' ─────────────────────────────────────
    # Means that weekday in the following calendar week (Monday to Sunday).
    # Always flagged 'ambiguous' because in casual college chat, students frequently
    # disagree whether 'next Wednesday' on a Tuesday means tomorrow or the week after.
    for name, target_weekday in WEEKDAYS.items():
        if cleaned in (f"next {name}", f"agle {name}"):
            current_monday = ref_date - timedelta(days=ref_date.weekday())
            target_date = current_monday + timedelta(days=7 + target_weekday)
            return target_date, "ambiguous"

    # ── Rule 6: Plain or 'this <weekday>' ────────────────────────────
    # Next occurrence on or after the reference date.
    # If sent on Friday saying 'Friday' or 'this Friday', resolves to that same Friday.
    for name, target_weekday in WEEKDAYS.items():
        if cleaned in (name, f"this {name}", f"is {name}", f"on {name}"):
            days_ahead = (target_weekday - ref_date.weekday()) % 7
            return ref_date + timedelta(days=days_ahead), "ok"

    # ── Rule 7: Unresolved fallback ──────────────────────────────────
    # Plain text with no resolvable date (e.g. 'before next class', 'after lab').
    # Never guess.
    return None, "unresolved"
