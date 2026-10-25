import csv
import os
import re
import math
from collections import defaultdict, Counter


def keyword_baseline_predict(text: str) -> bool:
    lowered = text.lower()
    patterns = [
        r\"submit\", r\"submission\", r\"assignment\", r\"deadline\", r\"\bdue\b\", r\"exam\", r\"\btest\b\", r\"viva\",
        r\"lab record\", r\"report\", r\"before\", r\"by tomorrow\", r\"jama karna\", r\"jama\", r\"last date\",
        r\"project\", r\"quiz\", r\"internal\", r\"practical\"
    ]
    for p in patterns:
        if re.search(p, lowered):
            return True
    return False


def read_labeled(path):
    rows = []
    with open(path, newline=\"\", encoding=\"utf-8\") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


class MultinomialNaiveBayes:
    \"\"\"
    Pure-Python multinomial Naive Bayes text classifier.
    Tokenises with re (lowercased). Uses unigrams + bigrams.
    Laplace smoothing alpha=1, log-probabilities for numerical stability.
    \"\"\"
    def __init__(self, alpha=1.0):
        self.alpha = alpha
        self.class_log_prior = {}
        self.feature_log_prob = {}
        self.vocab = set()
        self.classes = []

    def _tokenize(self, text):
        tokens = re.findall(r'\b\w+\b', text.lower())
        features = list(tokens)
        for a, b in zip(tokens, tokens[1:]):
            features.append(a + ' ' + b)
        return features

    def fit(self, X, y):
        self.classes = list(set(y))
        n_docs = len(y)
        class_counts = Counter(y)
        for c in self.classes:
            self.class_log_prior[c] = math.log(class_counts[c] / n_docs)
        word_count = {c: Counter() for c in self.classes}
        for xi, yi in zip(X, y):
            for f in self._tokenize(xi):
                word_count[yi][f] += 1
                self.vocab.add(f)
        for c in self.classes:
            total = sum(word_count[c].values())
            self.feature_log_prob[c] = {}
            for f in self.vocab:
                count = word_count[c].get(f, 0)
                self.feature_log_prob[c][f] = math.log((count + self.alpha) / (total + self.alpha * len(self.vocab)))

    def predict(self, X):
        preds = []
        for xi in X:
            feats = self._tokenize(xi)
            scores = {}
            for c in self.classes:
                score = self.class_log_prior.get(c, -1e18)
                for f in feats:
                    if f in self.feature_log_prob[c]:
                        score += self.feature_log_prob[c][f]
                    else:
                        score += math.log(self.alpha / (sum(self.feature_log_prob[c].values()) + self.alpha * len(self.vocab)))
                scores[c] = score
            preds.append(max(scores.items(), key=lambda x: x[1])[0])
        return preds


def train_tfidf_logreg(train_rows):
    \"\"\"Train a pure-Python multinomial Naive Bayes classifier on dev split rows.\"\"\"
    X = [r.get(\"text\", \"\") for r in train_rows]
    y = [1 if r.get(\"gold_label\") == \"commitment\" else 0 for r in train_rows]
    clf = MultinomialNaiveBayes(alpha=1.0)
    if len(set(y)) >= 1:
        clf.fit(X, y)
    return clf


def evaluate_tfidf_logreg(labeled_csv_path):
    rows = read_labeled(labeled_csv_path)
    train_rows = [r for r in rows if r.get(\"split\") == \"dev\"]
    test_rows = [r for r in rows if r.get(\"split\") == \"test\"]
    pipe = train_tfidf_logreg(train_rows)
    preds = {}
    for r in test_rows:
        mid = r[\"message_id\"]
        try:
            pred = pipe.predict([r.get(\"text\", \"\")])[0]
        except Exception:
            pred = 0
        preds[mid] = bool(pred)
    return preds, test_rows


def evaluate_keyword(labeled_csv_path):
    rows = read_labeled(labeled_csv_path)
    test_rows = [r for r in rows if r.get(\"split\") == \"test\"]
    preds = {}
    for r in test_rows:
        mid = r[\"message_id\"]
        preds[mid] = keyword_baseline_predict(r.get(\"text\", \"\"))
    return preds, test_rows
