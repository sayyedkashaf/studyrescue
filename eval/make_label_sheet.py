import csv

from app.ingest.whatsapp_parser import parse_whatsapp_export


def build_sheet(txt_path, out_csv_path):
    with open(txt_path, encoding='utf-8') as f:
        raw = f.read()
    messages = parse_whatsapp_export(raw)
    fieldnames = [
        "message_id", "text", "sent_at", "gold_label", "gold_kind",
        "gold_deadline_text", "gold_deadline_date", "split", "error_tags", "notes",
    ]
    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for m in messages:
            writer.writerow([
                m.line_no,
                m.text,
                m.sent_at.isoformat() if m.sent_at else "",
                "", "", "", "", "", "", "",
            ])
