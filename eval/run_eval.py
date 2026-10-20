import csv
import json
import os

from eval.metrics import prf
from app.ai.extractor import extract_from_messages


def load_labeled(csv_path, split) -> list[dict]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("split") == split and (row.get("gold_label") or "").strip() != "":
                rows.append(row)
    return rows


def score(rows, predictions) -> dict:
    tp = fp = fn = tn = 0
    error_rows = []
    for row in rows:
        mid = row["message_id"]
        pred = predictions.get(mid)
        if pred is None and str(mid).isdigit():
            pred = predictions.get(int(mid))
        if pred is None:
            pred = predictions.get(str(mid), False)
        gold_positive = row.get("gold_label") == "commitment"
        if pred and gold_positive:
            tp += 1
        elif pred and not gold_positive:
            fp += 1
            error_rows.append(row)
        elif (not pred) and gold_positive:
            fn += 1
            error_rows.append(row)
        else:
            tn += 1
    prf_result = prf(tp, fp, fn)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": prf_result["precision"],
        "recall": prf_result["recall"],
        "f1": prf_result["f1"],
        "prf": prf_result,
        "error_rows": error_rows,
    }


def llm_predict(rows, cache_path) -> dict[int, bool]:
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = []
        chunk_size = 20
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            messages = [
                {"id": int(r["message_id"]) if str(r["message_id"]).isdigit() else r["message_id"],
                 "sent_at": r["sent_at"],
                 "text": r["text"]}
                for r in chunk
            ]
            raw.extend(extract_from_messages(messages))
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(raw, f)

    result = {}
    for r in rows:
        mid = int(r["message_id"]) if str(r["message_id"]).isdigit() else r["message_id"]
        result[mid] = False
    for c in raw:
        mid = c.get("message_id")
        if mid in result and not c.get("is_joke_or_hypothetical"):
            result[mid] = True
        elif str(mid).isdigit() and int(mid) in result and not c.get("is_joke_or_hypothetical"):
            result[int(mid)] = True
    return result


import argparse
from datetime import datetime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()

    if args.split == "test" and not args.final:
        print("Refusing to run on test split without --final flag.")
        return

    if args.final:
        os.makedirs("eval/reports", exist_ok=True)
        with open("eval/reports/final_runs.log", "a", encoding="utf-8") as f:
            f.write(datetime.now().isoformat() + "\n")


if __name__ == "__main__":
    main()

def write_report(split, n_rows, baseline_result, llm_result, out_path):
    lines = []
    lines.append(f"# Eval Report - {split}")
    lines.append("")
    lines.append(f"Dataset size: {n_rows}")
    lines.append("")
    lines.append("| Method | Precision | Recall | F1 |")
    lines.append("|---|---|---|---|")
    lines.append(f"| baseline | {baseline_result['precision']:.4f} | {baseline_result['recall']:.4f} | {baseline_result['f1']:.4f} |")
    lines.append(f"| llm | {llm_result['precision']:.4f} | {llm_result['recall']:.4f} | {llm_result['f1']:.4f} |")
    lines.append("")
    lines.append("| message text | gold label | prediction | reason |")
    lines.append("|---|---|---|---|")
    for row in llm_result.get("error_rows", []):
        text = str(row.get("text", "")).replace("|", "\\|").replace("\n", " ")
        gold = row.get("gold_label", "")
        pred = "not commitment" if gold == "commitment" else "commitment"
        lines.append(f"| {text} | {gold} | {pred} |  |")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
