import csv
import random

from app.ingest.whatsapp_parser import parse_whatsapp_export


def build_sheet(txt_path, out_csv_path):
    with open(txt_path, encoding='utf-8') as f:
        raw = f.read()
    messages = parse_whatsapp_export(raw)
    rng = random.Random(42)
    dates = []
    for m in messages:
        if m.sent_at:
            dates.append(m.sent_at.date())
        else:
            dates.append(None)
    unique_dates = []
    seen = set()
    for d in dates:
        key = id(d) if d is None else d
        if d not in seen:
            seen.add(d)
            unique_dates.append(d)
    date_splits = {}
    for d in unique_dates:
        date_splits[d] = "dev" if rng.random() < 0.6 else "test"
    fieldnames = [
        "message_id", "text", "sent_at", "gold_label", "gold_kind",
        "gold_deadline_text", "gold_deadline_date", "split", "error_tags", "notes",
    ]
    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for i, m in enumerate(messages):
            d = dates[i]
            split = date_splits.get(d, "dev")
            writer.writerow([
                m.line_no,
                m.text,
                m.sent_at.isoformat() if m.sent_at else "",
                "", "", "", "", split, "", "",
            ])
