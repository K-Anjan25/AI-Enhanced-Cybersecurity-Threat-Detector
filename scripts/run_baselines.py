#!/usr/bin/env python3
"""Train and score the baseline models on a real dataset (T-110).

Reads a fetched dataset, cuts it into windows, splits it under both leakage
invariants, extracts ``features@1``, fits a scaler on the training fold only,
then fits and scores logistic regression and gradient boosting. Metrics come
from the same evaluation harness the transformers will be judged by, so a
baseline number and a model number are directly comparable.

Writes a run log (JSON) containing the dataset hash, the split audit, the model
configuration and the full metric set, so a number quoted in memory.md can be
traced back to the exact artifact that produced it.

Usage::

    python scripts/run_baselines.py --file Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv
    python scripts/run_baselines.py --file ... --limit 40000 --stumps 30
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections.abc import Sequence
from typing import cast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml-service"))

from aegis_ml.data.features import (  # noqa: E402
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    FlowFeatures,
    extract_flow_window,
)
from aegis_ml.data.parsers import (  # noqa: E402
    ParseReport,
    parse_cic_ids2017,
    parse_unsw_nb15,
)
from aegis_ml.data.preprocess import (  # noqa: E402
    Preprocessor,
    StandardScaler,
    Vocabulary,
)
from aegis_ml.data.records import FlowRecord  # noqa: E402
from aegis_ml.data.splits import Split, split_windows  # noqa: E402
from aegis_ml.data.windowing import Window, WindowKey, window_flows  # noqa: E402
from aegis_ml.training.baselines import (  # noqa: E402
    DEFAULT_LR_EPOCHS,
    DEFAULT_STUMP_COUNT,
    GradientBoostedStumps,
    LogisticRegression,
    design_matrix,
)
from aegis_ml.training.evaluation import EvalReport, evaluate  # noqa: E402

PARSERS = {
    "cic-ids2017": parse_cic_ids2017,
    "unsw-nb15": parse_unsw_nb15,
}


def _read_ndjson(path: str) -> list[FlowRecord]:
    """Load flow@1 records written by the synthetic generator or the ingest path."""
    records: list[FlowRecord] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(FlowRecord.model_validate_json(line))
    return records


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _features(
    windows: Sequence[Window[FlowRecord]], key: WindowKey
) -> list[FlowFeatures]:
    """Extract ``features@1`` rows for every flow in every window.

    ``extract_flow_window`` yields one row per flow — per-flow measurements
    alongside the window-level statistics — so the unit scored here is a flow
    carrying its window's context. The split is made at window level, so every
    row belonging to a window lands in the same fold and no row can leak.
    """
    out: list[FlowFeatures] = []
    for window in windows:
        out.extend(extract_flow_window(window.records, key=key))
    return out


def _subsample(
    rows: list[list[float]], targets: list[int], cap: int
) -> tuple[list[list[float]], list[int]]:
    """Thin the training rows to ``cap`` by a fixed stride.

    A stride rather than a random draw, so two runs select the same rows and the
    result stays reproducible (R-67). Test rows are never thinned: the metric
    has to describe the whole held-out fold, not a convenient part of it.
    """
    if cap <= 0 or len(rows) <= cap:
        return rows, targets
    stride = -(-len(rows) // cap)  # ceil, so the result never exceeds cap
    return rows[::stride], targets[::stride]


def _fit_preprocessor(train: Sequence[FlowFeatures]) -> Preprocessor:
    """Fit scaler and vocabularies on the training fold alone (R-62)."""
    scaler = StandardScaler.fit([list(w.numeric) for w in train], NUMERIC_FEATURES)
    vocabularies = {
        name: Vocabulary.fit(w.categorical[index] for w in train)
        for index, name in enumerate(CATEGORICAL_FEATURES)
    }
    return Preprocessor(scaler=scaler, vocabularies=vocabularies)


def _metrics(report: EvalReport) -> dict[str, object]:
    """The report as plain data, so it can go straight into the run log."""
    return cast("dict[str, object]", json.loads(report.model_dump_json()))


def main(argv: list[str] | None = None) -> int:
    """Run the baselines and write a run log. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--file",
        required=True,
        action="append",
        help="Input file under data/. Repeatable to combine capture days.",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "ndjson"],
        default="csv",
        help="csv for a fetched dataset, ndjson for flow@1 records.",
    )
    parser.add_argument("--dataset", choices=sorted(PARSERS), default="cic-ids2017")
    parser.add_argument("--key", choices=["source", "destination"], default="source")
    parser.add_argument(
        "--limit", type=int, default=0, help="Parse only the first N rows."
    )
    parser.add_argument("--epochs", type=int, default=DEFAULT_LR_EPOCHS)
    parser.add_argument(
        "--max-train-rows",
        type=int,
        default=15000,
        help="Deterministically thin the training rows to this many.",
    )
    parser.add_argument("--stumps", type=int, default=DEFAULT_STUMP_COUNT)
    parser.add_argument("--out", default="data/runs/baselines.json")
    args = parser.parse_args(argv)

    paths = [f if os.path.isabs(f) else os.path.join(ROOT, f) for f in args.file]
    paths = [
        (
            p
            if os.path.isfile(p) or args.format == "ndjson"
            else os.path.join(ROOT, "data", "raw", os.path.basename(p))
        )
        for p in paths
    ]
    key = WindowKey.SOURCE if args.key == "source" else WindowKey.DESTINATION
    started = time.time()

    reports: list[ParseReport] = []
    source_sha: dict[str, str] = {}
    chunks: list[Sequence[FlowRecord]] = []
    for path in paths:
        print(f"reading {path}")
        source_sha[os.path.basename(path)] = _sha256(path)
        if args.format == "ndjson":
            chunk: Sequence[FlowRecord] = tuple(_read_ndjson(path))
            print(f"  {len(chunk):,} flow@1 records")
        else:
            parsed = PARSERS[args.dataset](path)
            parsed.report.raise_for_empty()
            reports.append(parsed.report)
            unmapped = len(parsed.report.unmapped_columns)
            print(
                f"  {parsed.report.parsed:,} of {parsed.report.rows_read:,} rows parsed "
                f"({parsed.report.rejected:,} rejected); unmapped columns: {unmapped}"
            )
            chunk = parsed.records
        chunks.append(chunk)
    # Combining capture days is what makes a tail test fold contain attacks at
    # all: on a single day the burst ends before the test period starts.
    records = tuple(record for chunk in chunks for record in chunk)
    print(f"  combined: {len(records):,} records from {len(paths)} file(s)")
    if args.limit:
        records = tuple(records[: args.limit])
        print(f"  limited to the first {len(records):,} records")

    # window_flows requires arrival order (a window that was not observed in
    # order has no meaningful inter-arrival statistics). A live capture arrives
    # ordered; a benchmark CSV need not be. sorted() is stable, so flows sharing
    # a timestamp keep their file order rather than being shuffled between runs.
    records = tuple(sorted(records, key=lambda record: record.timestamp))

    windows = window_flows(records, key=key)
    print(f"  {len(windows):,} windows keyed by {key.value}")

    split: Split[FlowRecord] = split_windows(windows)
    audit = split.audit()
    print(f"  split: {audit}")
    if not (audit["test_after_train"] and audit["entities_disjoint"]):
        print(
            "refusing to train: the split violates a leakage invariant", file=sys.stderr
        )
        return 1

    train = _features(split.train, key)
    valid = _features(split.valid, key)
    test = _features(split.test, key)
    print(
        f"  feature rows: train={len(train):,} valid={len(valid):,} test={len(test):,}"
    )
    if not train or not test:
        print("refusing to train: a fold produced no feature rows", file=sys.stderr)
        return 1

    # The scaler sees every training row even when fitting is done on a thinned
    # subset: statistics computed on a subset of train are still train-only, but
    # using all of them costs nothing and is strictly better.
    preprocessor = _fit_preprocessor(train)
    all_train_rows, all_train_targets = design_matrix(train, preprocessor)
    test_rows, test_targets = design_matrix(test, preprocessor)

    # A fold holding only one class cannot produce a ranking metric, and the
    # failure is a property of the data rather than of the model. Report it as
    # such instead of letting it surface as a crash from inside the harness.
    for fold, targets in (("train", all_train_targets), ("test", test_targets)):
        positives = sum(targets)
        if positives in (0, len(targets)):
            print(
                f"refusing to train: the {fold} fold holds a single class "
                f"({len(targets):,} rows, {positives:,} positive). Under a strictly "
                "temporal, entity-disjoint split a short attack burst from ephemeral "
                "sources can fall entirely inside the training period (D-014).",
                file=sys.stderr,
            )
            return 1
    train_rows, train_targets = _subsample(
        all_train_rows, all_train_targets, args.max_train_rows
    )
    print(
        f"  design matrix: {len(train_rows[0])} columns; "
        f"fitting on {len(train_rows):,} of {len(all_train_rows):,} train rows"
    )

    results: dict[str, object] = {}
    print(f"fitting logistic regression ({args.epochs} epochs)")
    logistic = LogisticRegression.fit(train_rows, train_targets, epochs=args.epochs)
    results["logistic_regression"] = _metrics(
        evaluate(
            [logistic.score(r) for r in test_rows],
            [bool(t) for t in test_targets],
            model_id="baseline-logreg",
        )
    )

    print(f"fitting gradient boosting ({args.stumps} stumps)")
    boosted = GradientBoostedStumps.fit(train_rows, train_targets, n_stumps=args.stumps)
    results["gradient_boosting"] = _metrics(
        evaluate(
            [boosted.score(r) for r in test_rows],
            [bool(t) for t in test_targets],
            model_id="baseline-gbdt",
        )
    )

    log = {
        "dataset": args.dataset,
        "source_files": [os.path.basename(p) for p in paths],
        "source_sha256": source_sha,
        "window_key": key.value,
        "rows_read": sum(r.rows_read for r in reports) if reports else len(records),
        "rows_parsed": len(records),
        "rows_rejected": sum(r.rejected for r in reports),
        "rejection_reasons": {
            reason: sum(r.rejection_reasons.get(reason, 0) for r in reports)
            for reason in sorted({k for r in reports for k in r.rejection_reasons})
        },
        "split": audit,
        "feature_rows": {
            "train": len(all_train_rows),
            "valid": len(valid),
            "test": len(test),
        },
        "train_rows_fitted": len(train_rows),
        "positive_rate_train": sum(train_targets) / len(train_targets),
        "positive_rate_test": sum(test_targets) / len(test_targets),
        "models": results,
        "elapsed_seconds": round(time.time() - started, 2),
    }

    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(log, handle, indent=2, sort_keys=True)
    print(f"\nrun log written to {out}")

    for name, payload in results.items():
        entry = cast("dict[str, object]", payload)
        metrics = cast("dict[str, float]", entry["metrics"])
        print(
            f"  {name:<22} precision={metrics['precision']:.4f} recall={metrics['recall']:.4f} "
            f"f1={metrics['f1']:.4f} roc_auc={metrics['roc_auc']:.4f} "
            f"pr_auc={metrics['pr_auc']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
