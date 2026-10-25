import argparse
import csv
import json
import os
import random
import time
from datetime import datetime

from eval.baselines import keyword_baseline_predict, train_tfidf_logreg
from app.ai.extractor import extract_from_messages


def load_labeled(csv_path, split):
    rows = []
    with open(csv_path, newline=\"\", encoding=\"utf-8\") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get(\"split\") == split and (row.get(\"gold_label\") or \"\").strip() != \"\":
                rows.append(row)
    return rows


def score(rows, predictions):
    tp = fp = fn = tn = 0
    error_rows = []
    for row in rows:
        mid = row[\"message_id\"]
        pred = predictions.get(mid)
        if pred is None and str(mid).isdigit():
            pred = predictions.get(int(mid))
        if pred is None:
            pred = predictions.get(str(mid), False)
        gold_positive = row.get(\"gold_label\") == \"commitment\"
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
    from eval.metrics import prf
    prf_result = prf(tp, fp, fn)
    return {\"tp\": tp, \"fp\": fp, \"fn\": fn, \"tn\": tn, \"precision\": prf_result[\"precision\"], \"recall\": prf_result[\"recall\"], \"f1\": prf_result[\"f1\"], \"prf\": prf_result, \"error_rows\": error_rows}


def _read_labelled(path):
    rows = []
    with open(path, newline=\"\", encoding=\"utf-8\") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _get_pred(preds, mid):
    p = preds.get(mid)
    if p is None and str(mid).isdigit():
        p = preds.get(int(mid))
    if p is None:
        p = preds.get(str(mid), False)
    return bool(p)


def confusion(y_true, y_pred):
    tp = fp = fn = tn = 0
    for t, p in zip(y_true, y_pred):
        if p and t:
            tp += 1
        elif p and not t:
            fp += 1
        elif (not p) and t:
            fn += 1
        else:
            tn += 1
    return {\"tp\": tp, \"fp\": fp, \"fn\": fn, \"tn\": tn}


def prf_from_cm(cm):
    tp, fp, fn = cm[\"tp\"], cm[\"fp\"], cm[\"fn\"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {\"precision\": precision, \"recall\": recall, \"f1\": f1}


def bootstrap_ci(y_true, y_pred, metric=\"f1\", n=1000, seed=123):
    rng = random.Random(seed)
    idxs = list(range(len(y_true)))
    samples = []
    for _ in range(n):
        s_idx = [rng.choice(idxs) for _ in idxs]
        yt = [y_true[i] for i in s_idx]
        yp = [y_pred[i] for i in s_idx]
        cm = confusion(yt, yp)
        p = prf_from_cm(cm)
        samples.append(p[metric])
    samples.sort()
    low = samples[int(0.025 * n)]
    high = samples[int(0.975 * n)]
    return low, high


def gemini_predict(rows, cache_dir=\"eval/cache\"):
    os.makedirs(cache_dir, exist_ok=True)
    preds = {}
    cache = {}
    for r in rows:
        key = r.get(\"text\", \"\")
        cpath = os.path.join(cache_dir, str(hash(key)) + \".json\")
        if os.path.exists(cpath):
            with open(cpath) as f:
                cache[key] = json.load(f)
    for r in rows:
        mid = r[\"message_id\"]
        text = r.get(\"text\", \"\")
        if text in cache:
            preds[mid] = cache[text]
            continue
        msg = [{\"id\": mid, \"sent_at\": r.get(\"sent_at\") or \"2026-01-01T00:00:00\", \"text\": text}]
        for attempt in range(3):
            try:
                res = extract_from_messages(msg)
                pred = any(c.get(\"is_joke_or_hypothetical\") is False for c in res)
                preds[mid] = pred
                cpath = os.path.join(cache_dir, str(hash(text)) + \".json\")
                with open(cpath, \"w\") as f:
                    json.dump(pred, f)
                break
            except Exception:
                time.sleep(0.1 * (attempt + 1))
        else:
            preds[mid] = keyword_baseline_predict(text)
    return preds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(\"--split\", choices=[\"dev\", \"test\"], required=False)
    parser.add_argument(\"--final\", action=\"store_true\")
    args = parser.parse_args()
    split = getattr(args, \"split\", None) or \"dev\"

    if split == \"test\" and not args.final:
        print(\"Refusing to run on test split without --final flag.\")
        return
    try:
        labeled_path = f\"eval/labeled/{split}.csv\"
        if not os.path.exists(labeled_path):
            labeled_path = \"eval/labeled/labeled_messages.csv\"
        rows = load_labeled(labeled_path, split)
    except Exception:
        return

    gold = [r.get(\"gold_label\") == \"commitment\" for r in rows]
    mids = [r[\"message_id\"] for r in rows]

    kpred = [keyword_baseline_predict(r.get(\"text\", \"\")) for r in rows]
    kcm = confusion(gold, kpred)
    kp = prf_from_cm(kcm)

    train_rows = _read_labelled(labeled_path)
    train_rows = [r for r in train_rows if r.get(\"split\") == \"dev\"]
    pipe = train_tfidf_logreg(train_rows)
    tpred = []
    for r in rows:
        try:
            tpred.append(bool(pipe.predict([r.get(\"text\", \"\")])[0]))
        except Exception:
            tpred.append(False)
    tcm = confusion(gold, tpred)
    tp = prf_from_cm(tcm)

    gp = gemini_predict(rows)
    gpred = [_get_pred(gp, m) for m in mids]
    gcm = confusion(gold, gpred)
    gprf = prf_from_cm(gcm)

    def _has_unsure(r):
        tags = (r.get(\"error_tags\") or \"\").lower()
        return \"unsure\" in tags

    subset2 = [r for r in rows if not _has_unsure(r)]
    gold2 = [r.get(\"gold_label\") == \"commitment\" for r in subset2]
    kpred2 = [keyword_baseline_predict(r.get(\"text\", \"\")) for r in subset2]
    mids2 = [r[\"message_id\"] for r in subset2]
    try:
        tpred2 = [bool(pipe.predict([r.get(\"text\", \"\")])[0]) for r in subset2]
    except Exception:
        tpred2 = [False for _ in subset2]
    gp2 = gemini_predict(subset2)
    gpred2 = [_get_pred(gp2, m) for m in mids2]

    tags = [\"joke\", \"hypothetical\", \"vague\", \"hinglish\", \"forwarded\", \"past_event\"]
    by_tag = {}
    for tag in tags:
        tagged = [r for r in rows if tag in (r.get(\"error_tags\") or \"\").lower()]
        if not tagged:
            continue
        tg = [r.get(\"gold_label\") == \"commitment\" for r in tagged]
        tm = [r[\"message_id\"] for r in tagged]
        tk = [keyword_baseline_predict(r.get(\"text\", \"\")) for r in tagged]
        tt = []
        for r in tagged:
            try:
                tt.append(bool(pipe.predict([r.get(\"text\", \"\")])[0]))
            except Exception:
                tt.append(False)
        tgp = gemini_predict(tagged)
        tgpr = [_get_pred(tgp, m) for m in tm]
        by_tag[tag] = {
            \"keyword\": prf_from_cm(confusion(tg, tk)),
            \"tfidf\": prf_from_cm(confusion(tg, tt)),
            \"gemini\": prf_from_cm(confusion(tg, tgpr)),
        }

    results = {
        \"split\": split,
        \"keyword\": {**kp, \"cm\": kcm, \"ci\": {\"f1\": bootstrap_ci(gold, kpred, \"f1\")}},
        \"tfidf\": {**tp, \"cm\": tcm, \"ci\": {\"f1\": bootstrap_ci(gold, tpred, \"f1\")}},
        \"gemini\": {**gprf, \"cm\": gcm, \"ci\": {\"f1\": bootstrap_ci(gold, gpred, \"f1\"), \"pinned_model\": os.environ.get(\"GEMINI_MODEL\") or os.environ.get(\"LLM_MODEL\")}},
        \"no_unsure\": {
            \"keyword\": prf_from_cm(confusion(gold2, kpred2)),
            \"tfidf\": prf_from_cm(confusion(gold2, tpred2)),
            \"gemini\": prf_from_cm(confusion(gold2, gpred2)),
        },
        \"by_tag\": by_tag,
    }

    os.makedirs(\"eval/results\", exist_ok=True)
    out = f\"eval/results/{split}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json\"
    with open(out, \"w\") as f:
        json.dump(results, f)
    print(results)


if __name__ == \"__main__\":
    main()
