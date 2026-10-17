"""
Hinglish and English date vocabulary and lookup tables.

Contains mappings for weekdays (English and Hinglish), months,
and relative day/week expressions commonly found in Indian student chat.
"""

# Weekdays mapped to integer 0 (Monday) .. 6 (Sunday)
WEEKDAYS: dict[str, int] = {
    # English full
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    # English short
    "mon": 0,
    "tue": 1,
    "tues": 1,
    "wed": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
    # Hinglish
    "somvar": 0,
    "somvaar": 0,
    "mangalvar": 1,
    "mangalvaar": 1,
    "budhvar": 2,
    "budhvaar": 2,
    "guruvar": 3,
    "guruvaar": 3,
    "veervar": 3,
    "veerwaar": 3,
    "brihaspativar": 3,
    "shukravar": 4,
    "shukravaar": 4,
    "shanivar": 5,
    "shanivaar": 5,
    "ravivar": 6,
    "ravivaar": 6,
    "itwar": 6,
    "itwaar": 6,
}

# Months mapped to 1..12
MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

# Relative day keywords mapped to (offset_days, flag, explanation)
RELATIVE_DAYS: dict[str, tuple[int, str]] = {
    "today": (0, "ok"),
    "aaj": (0, "ok"),
    "tomorrow": (1, "ok"),
    # 'kal' is always flagged 'ambiguous' because in Hindi/Hinglish
    # it can mean either tomorrow or yesterday depending on context
    "kal": (1, "ambiguous"),
    "day after tomorrow": (2, "ok"),
    "parso": (2, "ok"),
    "parson": (2, "ok"),
    "eod": (0, "ok"),
}
