"""Score the blind evaluation.

Usage:  python eval/score.py [eval/sample_YYYY-MM-DD.csv]

Reads the human labels (open | claimed | stale_claim | restricted | unsure), joins
the classifier labels that `run.py sample-eval` stored separately in
eval/.hidden_YYYY-MM-DD.json (so the labeller never saw them), and reports
per-class precision and recall with Wilson 95 % intervals, plus the headline
"claimed-vs-open" binary precision (bar: >= 0.90). Writes eval/results.json,
which the exporter embeds in meta.json and the site shows on /methodology.

Binary mapping for the headline number: {claimed, stale_claim} -> "taken";
{open, restricted} -> "free". Precision of "free" is what a newcomer cares about
most: when we say an issue is free, how often is it actually free? Both
directions are reported.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAR = 0.90
CLASSES = ["open", "claimed", "stale_claim", "restricted"]


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def prf(gold: list[str], pred: list[str], cls: str) -> dict:
    tp = sum(1 for g, p in zip(gold, pred) if g == cls and p == cls)
    fp = sum(1 for g, p in zip(gold, pred) if g != cls and p == cls)
    fn = sum(1 for g, p in zip(gold, pred) if g == cls and p != cls)
    prec_n, rec_n = tp + fp, tp + fn
    return {"tp": tp, "fp": fp, "fn": fn, "precision": tp / prec_n if prec_n else None, "precision_ci": wilson(tp, prec_n),
            "recall": tp / rec_n if rec_n else None, "recall_ci": wilson(tp, rec_n), "support": rec_n}


def main(argv: list[str]) -> int:
    samples = sorted(HERE.glob("sample_*.csv"))
    path = Path(argv[1]) if len(argv) > 1 else (samples[-1] if samples else None)
    if not path or not path.exists():
        print("no sample file; run `python pipeline/run.py sample-eval` first")
        return 1
    date = path.stem.replace("sample_", "")
    hidden_path = HERE / f".hidden_{date}.json"
    if not hidden_path.exists():
        print(f"missing {hidden_path}; the classifier labels for this sample are gone")
        return 1
    hidden = json.loads(hidden_path.read_text(encoding="utf-8"))
    gold, pred, skipped = [], [], Counter()
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            h = (row.get("human_label") or "").strip().lower()
            if h not in CLASSES:
                skipped["unsure" if h == "unsure" else "blank/invalid"] += 1
                continue
            p = hidden.get(row["issue_url"])
            if p is None:
                skipped["no_classifier_label"] += 1
                continue
            gold.append(h)
            pred.append(p)
    n = len(gold)
    if n == 0:
        print("no labelled rows yet")
        return 1
    per_class = {c: prf(gold, pred, c) for c in CLASSES}
    taken = {"claimed", "stale_claim"}
    g_bin = ["taken" if g in taken else "free" for g in gold]
    p_bin = ["taken" if p in taken else "free" for p in pred]
    free = prf(g_bin, p_bin, "free")
    taken_m = prf(g_bin, p_bin, "taken")
    accuracy = sum(1 for g, p in zip(gold, pred) if g == p) / n
    confusion = defaultdict(Counter)
    for g, p in zip(gold, pred):
        confusion[g][p] += 1
    headline = min(x for x in (free["precision"], taken_m["precision"]) if x is not None)
    bar_met = headline >= BAR and n >= 150
    results = {
        "sample_date": date, "n": n, "skipped": dict(skipped), "accuracy": accuracy,
        "precision_claimed": taken_m["precision"], "recall_claimed": taken_m["recall"],
        "precision_open": free["precision"], "recall_open": free["recall"],
        "ci": {"precision_claimed": taken_m["precision_ci"], "recall_claimed": taken_m["recall_ci"], "precision_open": free["precision_ci"], "recall_open": free["recall_ci"]},
        "per_class": per_class, "confusion": {g: dict(c) for g, c in confusion.items()}, "headline_precision": headline, "bar": BAR, "bar_met": bar_met,
        "note": "binary: taken={claimed,stale_claim}, free={open,restricted}; bar requires both binary precisions >= 0.90 and n >= 150",
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"n={n} accuracy={accuracy:.3f}")
    for name, m in (("free (open+restricted)", free), ("taken (claimed+stale)", taken_m)):
        lo, hi = m["precision_ci"]
        rlo, rhi = m["recall_ci"]
        print(f"{name:26s} precision={m['precision']:.3f} [{lo:.3f},{hi:.3f}]  recall={m['recall']:.3f} [{rlo:.3f},{rhi:.3f}]  support={m['support']}")
    for c in CLASSES:
        m = per_class[c]
        pr = f"{m['precision']:.3f}" if m["precision"] is not None else "n/a"
        rc = f"{m['recall']:.3f}" if m["recall"] is not None else "n/a"
        print(f"  {c:12s} precision={pr} recall={rc} support={m['support']}")
    print(f"bar (>= {BAR}, n >= 150): {'MET' if bar_met else 'NOT MET'}  -> wrote eval/results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
