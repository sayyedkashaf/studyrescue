"""Regex baseline for commitment-message classification.

Reads labeled messages from eval/labeled/labeled_messages.csv if present and
compares a keyword-regex heuristic against the gold_label column, printing
Precision, Recall, and F1-score for the baseline.
"""

import csv
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "eval", "labeled", "labeled_messages.csv")

COMMITMENT_KEYWORDS = [
    "submit",
    "assignment",
    "due",
    "test",
    "exam",
    "lab",
    "viva",
    "deadline",
    "form",
    "project",
]

COMMITMENT_RE = re.compile(
    r"\b(" + "|".join(COMMITMENT_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def predict(message):
    return "commitment" if COMMITMENT_RE.search(message) else "none"


def main():
    if not os.path.exists(CSV_PATH):
        print(f"Labeled messages file not found: {CSV_PATH}")
        print("No baseline metrics to compute.")
        return 0

    y_true = []
    y_pred = []

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            message = row.get("message", "")
            gold = row.get("gold_label", "").strip().lower()
            if not message or gold not in ("commitment", "none"):
                continue
            y_true.append(gold)
            y_pred.append(predict(message))

    if not y_true:
        print("No valid labeled rows found.")
        return 0

    tp = sum(1 for t, p in zip(y_true, y_pred) if t == "commitment" and p == "commitment")
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != "commitment" and p == "commitment")
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == "commitment" and p != "commitment")

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    print(f"Samples: {len(y_true)}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall: {recall:.4f}")
    print(f"F1-score: {f1:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
