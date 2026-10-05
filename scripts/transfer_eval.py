#!/usr/bin/env python
r"""Cross-dataset transfer: train on one corpus, score another (T-208, R-66).

    python scripts/transfer_eval.py \
        --source unsw_nb15_official_schema_sample.csv --source-dataset unsw-nb15 \
        --target Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv \
        --target-dataset cic-ids2017 --epochs 5 --out data/runs/transfer.json

R-66 makes this a release gate rather than a footnote: a detector that works on the
corpus it was trained on and collapses on the next one is not detecting attacks, it
is recognising a capture.

**Which head is scored matters more than the threshold does.** FlowNet carries two
heads and they need different things. The supervised ``anomaly_head`` needs positive
examples, and a family-holdout split by construction puts every attack family in the
held-out fold, leaving the training fold benign-only. A binary head trained with no
positives learns to emit a constant near zero, so it scores every window in the
target below 0.10 regardless of what the window contains. That is what the first
version of this script measured, and the zero recall it reported was a property of
the wrong head, not of the model.

The reconstruction head is the other one: it is trained unsupervised to reproduce
benign traffic, needs no labels at all, and is what makes FlowNet an anomaly
detector rather than a classifier. It is the signal that can transfer, and
``--signal supervised`` is kept only so the contrast stays reproducible.

**The operating point is fitted on the source and never on the target.** A threshold
chosen by watching target recall move is not a transfer result -- it is a threshold
chosen to produce the number you wanted. So the cut comes from T-207's
``fit_threshold`` over the source's benign validation scores, which the target has
no part in, and is then applied unchanged.

Two things are held fixed on purpose.

**The preprocessor is fit on the source's training fold and never refit.** Fitting
on the target would leak it (R-62) and would also destroy the measurement: a
scaler that has seen the target's distribution cannot show that the model
generalised. Target values are standardised with the *source's* mean and standard
deviation, so a feature whose scale differs between captures shows up as a
distribution shift rather than being silently normalised away.

**The leakage audit runs before training, on the source split.** A transfer number
computed from a leaking source run would be two errors multiplied.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml-service"))
sys.path.insert(0, ROOT)

from aegis_ml.data.audit import audit_trained, blocking_findings  # noqa: E402
from aegis_ml.data.features import extract_flow_window  # noqa: E402
from aegis_ml.data.records import FlowRecord  # noqa: E402
from aegis_ml.data.splits import (  # noqa: E402
    Split,
    family_split,
    group_split,
    split_windows,
)
from aegis_ml.data.windowing import Window, WindowKey, window_flows  # noqa: E402
from aegis_ml.models.flownet import per_window_reconstruction_error  # noqa: E402
from aegis_ml.scoring.thresholds import DEFAULT_QUANTILE, fit_threshold  # noqa: E402
from aegis_ml.training.evaluation import evaluate  # noqa: E402
from aegis_ml.training.pipeline import (
    DatasetDigest,
    TrainingConfig,
    train,
)  # noqa: E402

from scripts.train_flownet import PARSERS, _fit, _sequences  # noqa: E402

#: R-66's floor. Below this the transfer result blocks the release.
RECALL_FLOOR = 0.70


def _windows(path: str, dataset: str, key: WindowKey) -> tuple[Window[FlowRecord], ...]:
    """Parse and window one corpus."""
    resolved = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.isfile(resolved):
        resolved = os.path.join(ROOT, "data", "raw", os.path.basename(path))
    print(f"reading {resolved}")
    parsed = PARSERS[dataset](resolved)
    parsed.report.raise_for_empty()
    print(
        f"  {parsed.report.parsed:,} rows parsed ({parsed.report.rejected:,} rejected)"
    )
    # window_flows needs arrival order; a benchmark CSV need not be in it.
    records = sorted(parsed.records, key=lambda record: record.timestamp)
    return window_flows(records, key=key)


def main(argv: list[str] | None = None) -> int:
    """Train on the source, score the target, and gate on recall."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True)
    parser.add_argument(
        "--source-dataset", choices=sorted(PARSERS), default="unsw-nb15"
    )
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--target-dataset", choices=sorted(PARSERS), default="cic-ids2017"
    )
    parser.add_argument("--key", choices=("source", "destination"), default="source")
    parser.add_argument(
        "--split-policy",
        choices=("entity-disjoint", "temporal-only", "entity-only", "family-holdout"),
        default="family-holdout",
        help="applied to the source split only; the target is scored whole",
    )
    parser.add_argument("--holdout-family", action="append")
    parser.add_argument(
        "--signal",
        choices=("recon", "supervised"),
        default="recon",
        help=(
            "recon = per-window reconstruction error, the unsupervised anomaly signal; "
            "supervised = the label-trained head, which is degenerate on a benign-only "
            "training fold and is kept only to make that contrast reproducible"
        ),
    )
    parser.add_argument(
        "--quantile",
        type=float,
        default=DEFAULT_QUANTILE,
        help="quantile of the SOURCE benign validation scores that becomes the cut",
    )
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260114)
    parser.add_argument("--out", default="data/runs/transfer.json")
    args = parser.parse_args(argv)

    import torch  # noqa: PLC0415

    key = WindowKey.SOURCE if args.key == "source" else WindowKey.DESTINATION
    source_windows = _windows(args.source, args.source_dataset, key)
    target_windows = _windows(args.target, args.target_dataset, key)

    split: Split[Window[FlowRecord]]
    if args.split_policy == "family-holdout":
        if not args.holdout_family:
            print("family-holdout needs --holdout-family", file=sys.stderr)
            return 1
        split = family_split(source_windows, holdout=args.holdout_family)
    elif args.split_policy == "entity-only":
        split = group_split(source_windows)
    else:
        split = split_windows(
            source_windows, entity_disjoint=args.split_policy != "temporal-only"
        )
    print(f"source split {args.split_policy}: {split.audit()}")

    # T-203 before anything is trained: a transfer number from a leaking source
    # run would be two errors multiplied, and the second one hides the first.
    preprocessor = _fit(split.train, key)
    audit_rows = [
        list(feature.numeric)
        for window in split.train
        for feature in extract_flow_window(window.records, key=key)
    ]
    audit = audit_trained(split, preprocessor.scaler, audit_rows, fit_on=split.train)
    blockers = blocking_findings(audit, split)
    for finding in audit.findings:
        if finding not in blockers:
            print(f"  audit: declared by this policy, not blocking - {finding}")
    if blockers:
        for finding in blockers:
            print(f"leakage audit: {finding}", file=sys.stderr)
        print(
            "refusing to train: the leakage audit failed (T-203, R-62)", file=sys.stderr
        )
        return 1
    print("  leakage audit: no blocking findings (T-203)")

    train_seq, train_y, _ = _sequences(split.train, key, preprocessor, 50)
    valid_seq, _, _ = _sequences(split.valid, key, preprocessor, 50)
    # The target is scored with the SOURCE preprocessor and never refit. Refitting
    # on it would leak (R-62) and would also hide the distribution shift this task
    # exists to measure.
    target_seq, target_y, padded = _sequences(target_windows, key, preprocessor, 50)
    if not train_seq or not target_seq:
        print("a fold came out empty", file=sys.stderr)
        return 1
    attacks = sum(target_y)
    print(
        f"  {len(train_seq):,} source train windows -> "
        f"{len(target_seq):,} target windows ({attacks:,} attack, {padded:,} padded)"
    )
    if attacks == 0:
        print(
            "the target fold contains no attacks, so recall is undefined",
            file=sys.stderr,
        )
        return 1

    config = TrainingConfig(epochs=args.epochs, seed=args.seed)
    print(f"training on the source ({config.epochs} epochs)")
    model, losses = train(config, train_seq, train_y)
    model.eval()

    def score(rows: list[list[float]]) -> list[float]:
        """Score one batch of windows with the selected head."""
        if not rows:
            return []
        with torch.no_grad():
            tensor = torch.tensor(rows, dtype=torch.float32)
            output = model(tensor)
            if args.signal == "supervised":
                return [float(v) for v in torch.sigmoid(output.anomaly_logits)]
            return [float(v) for v in per_window_reconstruction_error(output, tensor)]

    # The cut is fitted on source benign scores only. The target contributes nothing
    # to it, which is the whole point: a threshold picked by watching target recall
    # is not evidence about the target.
    source_scores = score(valid_seq)
    threshold = fit_threshold(source_scores, quantile_=args.quantile)
    scores = score(target_seq)

    report = evaluate(
        scores,
        [bool(t) for t in target_y],
        model_id=config.model_id,
        threshold=threshold,
    )
    recall = float(report.recall)
    passed = recall >= RECALL_FLOOR

    print(f"  final source loss {losses[-1]:.5f}")
    print(f"  signal: {args.signal}")
    print(
        f"  threshold {threshold:.4f} fitted on {len(source_scores)} source benign "
        f"validation scores at quantile {args.quantile} (target-blind)"
    )
    print("at that threshold:")
    print(
        f"  recall {recall:.4f}  precision {report.precision:.4f}  f1 {report.f1:.4f}  "
        f"ROC-AUC {report.metrics.roc_auc:.4f}"
    )
    print(
        f"R-66 transfer recall {recall:.4f} against floor {RECALL_FLOOR}: "
        f"{'PASS' if passed else 'BLOCKS RELEASE'}"
    )

    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    summary = {
        "task": "T-208",
        "rule": "R-66",
        "source": {
            "file": args.source,
            "sha256": DatasetDigest.of(
                args.source
                if os.path.isabs(args.source)
                else os.path.join(ROOT, "data", "raw", os.path.basename(args.source))
            ).sha256,
            "split_policy": args.split_policy,
            "holdout_family": list(args.holdout_family or []),
            "train_windows": len(train_seq),
        },
        "target": {
            "file": args.target,
            "sha256": DatasetDigest.of(
                args.target
                if os.path.isabs(args.target)
                else os.path.join(ROOT, "data", "raw", os.path.basename(args.target))
            ).sha256,
            "windows": len(target_seq),
            "attack_windows": attacks,
            "padded_windows": padded,
            "preprocessor_refit": False,
        },
        "signal": args.signal,
        "threshold": threshold,
        "threshold_quantile": args.quantile,
        "threshold_fit_on": "source benign validation scores",
        "threshold_used_target_labels": False,
        "source_validation_windows": len(source_scores),
        "recall": recall,
        "precision": float(report.precision),
        "f1": float(report.f1),
        "roc_auc": float(report.metrics.roc_auc),
        "recall_floor": RECALL_FLOOR,
        "passed": passed,
        "report": json.loads(report.model_dump_json()),
    }
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")
    print(f"wrote {out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
