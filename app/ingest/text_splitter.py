"""
Pasted text splitter for Study Rescue.

Splits pasted text on blank lines or line breaks into ParsedMessage records.
If the pasted text looks like a WhatsApp chat export, delegates to the WhatsApp parser.
"""

from datetime import datetime
import re

from app.ingest.whatsapp_parser import (
    ParsedMessage,
    parse_whatsapp_export,
    _ANDROID_PREFIX,
    _IOS_PREFIX,
)


def is_whatsapp_format(raw_text: str) -> bool:
    """Detects whether raw text follows WhatsApp export conventions."""
    if not raw_text or not raw_text.strip():
        return False
    lines = raw_text.strip().splitlines()[:10]
    match_count = 0
    for line in lines:
        if _ANDROID_PREFIX.match(line.strip()) or _IOS_PREFIX.match(line.strip()):
            match_count += 1
    return match_count >= 1


def split_pasted_text(raw_text: str, reference: datetime | None = None) -> list[ParsedMessage]:
    """
    Splits pasted text into ParsedMessage objects.
    - If the text looks like a WhatsApp export, parses it via WhatsApp parser.
    - Otherwise, splits on double line breaks (paragraphs) or single lines.
    - sent_at is set to reference datetime (default: now).
    """
    if not raw_text or not raw_text.strip():
        return []

    if is_whatsapp_format(raw_text):
        return parse_whatsapp_export(raw_text)

    # Standard pasted text: normalize line endings
    text = raw_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    ref_time = reference or datetime.now()

    # Split into chunks based on double line breaks (paragraphs), or fallback to non-empty lines
    raw_chunks = re.split(r"\n\s*\n", text)
    messages: list[ParsedMessage] = []
    line_cursor = 1

    for chunk in raw_chunks:
        trimmed = chunk.strip()
        if trimmed:
            messages.append(
                ParsedMessage(
                    sent_at=ref_time,
                    sender_alias="Sender 1",
                    text=trimmed,
                    line_no=line_cursor,
                )
            )
        line_cursor += chunk.count("\n") + 2

    return messages
