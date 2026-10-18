"""
WhatsApp chat export parser for Study Rescue.

Supports Android and iOS export formats, day-first dates, 12h/24h times,
multi-line messages, system message filtering, and sender anonymisation.
"""

from dataclasses import dataclass
from datetime import datetime
import re


@dataclass
class ParsedMessage:
    sent_at: datetime | None
    sender_alias: str
    text: str
    line_no: int


# ── Regex Patterns ───────────────────────────────────────────────────

# Android: '12/10/26, 4:15 pm - Name: message' or '12/10/2026, 16:15 - Name: message'
# Note: \u202f is narrow non-breaking space used before am/pm on modern Android
_ANDROID_PREFIX = re.compile(
    r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:[\s\u202f\xa0]*[apAP][mM])?)\s*-\s*(.*)$"
)

# iOS: '[12/10/26, 4:15:30 PM] Name: message' or '[12/10/26, 4:15 PM] Name: message'
_IOS_PREFIX = re.compile(
    r"^\[(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:[\s\u202f\xa0]*[apAP][mM])?)\]\s*(.*)$"
)

# System message substrings to skip
_SYSTEM_PATTERNS = [
    "messages and calls are end-to-end encrypted",
    "created group",
    "joined",
    "left",
    "added",
    "removed",
    "changed the subject",
    "changed the group",
    "changed group",
    "<media omitted>",
    "this message was deleted",
    "you deleted this message",
]


def _parse_timestamp(date_str: str, time_str: str) -> datetime | None:
    """Parses day-first date and 12h or 24h time safely."""
    # Normalize date separators
    date_parts = re.split(r"[/-]", date_str.strip())
    if len(date_parts) != 3:
        return None

    try:
        day = int(date_parts[0])
        month = int(date_parts[1])
        year = int(date_parts[2])
        if year < 100:
            year += 2000
    except ValueError:
        return None

    # Clean time string (replace narrow no-break space)
    cleaned_time = re.sub(r"[\u202f\xa0]", " ", time_str.strip())

    # Try common formats
    formats = [
        "%I:%M:%S %p",
        "%I:%M %p",
        "%H:%M:%S",
        "%H:%M",
    ]
    parsed_time = None
    for fmt in formats:
        try:
            parsed_time = datetime.strptime(cleaned_time, fmt).time()
            break
        except ValueError:
            continue

    if not parsed_time:
        # Try without space before am/pm (e.g. '4:15pm')
        m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([apAP][mM])$", cleaned_time)
        if m:
            hr, mn, sc, ampm = m.groups()
            hour = int(hr)
            minute = int(mn)
            second = int(sc) if sc else 0
            if ampm.lower() == "pm" and hour != 12:
                hour += 12
            elif ampm.lower() == "am" and hour == 12:
                hour = 0
            try:
                return datetime(year, month, day, hour, minute, second)
            except ValueError:
                return None
        return None

    try:
        return datetime(
            year, month, day,
            parsed_time.hour, parsed_time.minute, parsed_time.second
        )
    except ValueError:
        return None


def parse_whatsapp_export(raw_text: str) -> list[ParsedMessage]:
    """
    Parses WhatsApp chat export text into anonymised ParsedMessage records.
    Returns an empty list on unparseable, empty, or invalid input.
    Never throws exceptions.
    """
    if not raw_text or not raw_text.strip():
        return []

    # Strip UTF-8 BOM if present
    text = raw_text.lstrip("\ufeff")

    # Normalize line endings to \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    messages: list[ParsedMessage] = []
    sender_aliases: dict[str, str] = {}
    current_msg: ParsedMessage | None = None

    def get_alias(raw_sender: str) -> str:
        s = raw_sender.strip()
        if s not in sender_aliases:
            sender_aliases[s] = f"Sender {len(sender_aliases) + 1}"
        return sender_aliases[s]

    def is_system_text(content: str) -> bool:
        low = content.lower().strip()
        for p in _SYSTEM_PATTERNS:
            if p in low:
                return True
        return False

    for idx, line in enumerate(lines, start=1):
        # Match Android or iOS timestamp prefix
        m_android = _ANDROID_PREFIX.match(line)
        m_ios = _IOS_PREFIX.match(line)
        m = m_android or m_ios

        if m:
            date_str, time_str, remainder = m.groups()

            # A message MUST have a 'Sender: text' format
            # If there is no colon or it's a system notice, it is skipped
            colon_idx = remainder.find(":")
            if colon_idx == -1:
                # System line (e.g. encryption notice, group created, etc.)
                current_msg = None
                continue

            raw_sender = remainder[:colon_idx].strip()
            msg_text = remainder[colon_idx + 1:].strip()

            # Skip system notices, media omitted, or deleted messages
            if is_system_text(remainder) or is_system_text(msg_text):
                current_msg = None
                continue

            sent_at = _parse_timestamp(date_str, time_str)
            alias = get_alias(raw_sender)

            current_msg = ParsedMessage(
                sent_at=sent_at,
                sender_alias=alias,
                text=msg_text,
                line_no=idx,
            )
            messages.append(current_msg)
        else:
            # Continuation of previous message (multi-line message)
            if current_msg is not None:
                # Append line to previous message text
                if line.strip():
                    current_msg.text += "\n" + line.strip()

    return messages
