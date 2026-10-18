#!/usr/bin/env python3
r"""Score a FlowNet checkpoint on a dataset it was not trained on (R-66).

Builds windows from the evaluation file exactly as ``train_flownet.py`` does, then scores
each window with the serving ``FlowNetScorer``. Attack windows are sampled, and benign
windows are sampled, to keep the run bounded on CPU; the sample sizes are written out.

Usage::

    python scripts/cross_dataset_eval.py \\
        --checkpoint data/checkpoints/flownet_unsw_sample \\
        --file data/raw/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv \\
        --dataset cic-ids2017 --out data/runs/cross_unsw_to_cic.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml-service"))

from aegis_ml.data.features import extract_flow_window  # noqa: E402
from aegis_ml.data.parsers import parse_cic_ids2017, parse_unsw_nb15  # noqa: E402
from aegis_ml.data.windowing import WindowKey, window_flows  # noqa: E402
from aegis_ml.serving.flownet_scorer import FlowNetScorer  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402

PARSERS = {"cic-ids2017": parse_cic_ids2017, "unsw-nb15": parse_unsw_nb15}
#: Benign labels as the parsers emit them. CIC uses "normal"; a BENIGN variant is kept.
BENIGN_LABELS = frozenset({"normal", "BENIGN", "Normal", "0"})


def _label_window(rows: list[object]) -> bool | None:
    """True for an attack window, False for benign, None when no flow is labelled."""
    labels = {row.label for row in rows if row.label is not None}  # type: ignore[attr-defined]
    if not labels:
        return None
    return any(label not in BENIGN_LABELS for label in labels)


def main(argv: list[str] | None = None) -> int:
    """Run the evaluation and write the result JSON."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--dataset", choices=sorted(PARSERS), default="cic-ids2017")
    parser.add_argument("--attack-sample", type=int, default=400)
    parser.add_argument("--benign-sample", type=int, default=1600)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    parsed = PARSERS[args.dataset](args.file)
    records = sorted(parsed.records, key=lambda record: record.timestamp)
    print(f"{len(records):,} records parsed ({parsed.report.rejected:,} rejected)")
    windows = window_flows(records, key=WindowKey.SOURCE)

    attack, benign = [], []
    for window in windows:
        verdict = _label_window(extract_flow_window(window.records, key=WindowKey.SOURCE))
        if verdict is None:
            continue
        (attack if verdict else benign).append(window)
    print(f"{len(windows):,} windows: {len(attack):,} attack, {len(benign):,} benign")

    rng = random.Random(args.seed)  # noqa: S311 - sampling, not security
    picked = [(w, 1) for w in rng.sample(attack, min(args.attack_sample, len(attack)))]
    picked += [(w, 0) for w in rng.sample(benign, min(args.benign_sample, len(benign)))]

    scorer = FlowNetScorer.load(args.checkpoint)
    scores = [scorer.score(window.records).score for window, _ in picked]
    truth = [label for _, label in picked]

    positives = sum(truth)
    tp = sum(1 for s, y in zip(scores, truth, strict=True) if y and s >= args.threshold)
    fp = sum(1 for s, y in zip(scores, truth, strict=True) if not y and s >= args.threshold)
    result = {
        "checkpoint": os.path.relpath(args.checkpoint, ROOT),
        "evaluated_file": os.path.basename(args.file),
        "dataset": args.dataset,
        "sample": {"attack": positives, "benign": len(truth) - positives, "seed": args.seed},
        "roc_auc": roc_auc_score(truth, scores),
        "pr_auc": average_precision_score(truth, scores),
        "threshold": args.threshold,
        "recall": tp / positives if positives else None,
        "precision": tp / (tp + fp) if (tp + fp) else None,
        "tp": tp,
        "fp": fp,
        "fn": positives - tp,
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
