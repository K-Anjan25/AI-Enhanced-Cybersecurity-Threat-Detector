#!/usr/bin/env python
r"""Train FlowNet through the T-202 pipeline and check its acceptance clause.

    python scripts/train_pipeline.py --file unsw_nb15_official_schema_sample.csv \
        --dataset unsw-nb15 --split-policy family-holdout --holdout-family Generic \
        --epochs 5 --out-dir data/runs/pipeline

T-202's acceptance is that two runs of one config agree within ±0.005 AUC. This
script runs the same config twice against the same data and reports the
difference, so the clause is measured rather than argued.

The data preparation is imported from ``train_flownet.py`` rather than copied:
two scripts that window and split data slightly differently produce two numbers
that cannot be compared, and comparing them is the entire point here.
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
from aegis_ml.training.evaluation import evaluate  # noqa: E402
from aegis_ml.training.pipeline import (  # noqa: E402
    DatasetDigest,
    RunManifest,
    TrainingConfig,
    git_state,
    seed_map,
    train,
)

from scripts.train_flownet import PARSERS, _fit, _sequences  # noqa: E402

#: T-202's acceptance tolerance on ROC-AUC between two runs of one config.
AUC_TOLERANCE = 0.005


def main(argv: list[str] | None = None) -> int:
    """Train twice under one config, compare, and write both manifests."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", required=True)
    parser.add_argument("--dataset", choices=sorted(PARSERS), default="cic-ids2017")
    parser.add_argument("--key", choices=("source", "destination"), default="source")
    parser.add_argument(
        "--split-policy",
        choices=("entity-disjoint", "temporal-only", "entity-only", "family-holdout"),
        default="family-holdout",
    )
    parser.add_argument("--holdout-family", action="append")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=20260114)
    parser.add_argument("--runs", type=int, default=2, help="how many runs to compare")
    parser.add_argument("--out-dir", default="data/runs/pipeline")
    args = parser.parse_args(argv)

    import torch  # noqa: PLC0415

    path = args.file if os.path.isabs(args.file) else os.path.join(ROOT, args.file)
    if not os.path.isfile(path):
        path = os.path.join(ROOT, "data", "raw", os.path.basename(args.file))
    print(f"reading {path}")
    parsed = PARSERS[args.dataset](path)
    parsed.report.raise_for_empty()
    print(
        f"  {parsed.report.parsed:,} rows parsed ({parsed.report.rejected:,} rejected)"
    )

    key = WindowKey.SOURCE if args.key == "source" else WindowKey.DESTINATION
    records = sorted(parsed.records, key=lambda record: record.timestamp)
    windows = window_flows(records, key=key)
    print(f"  {len(windows):,} windows keyed by {key.value}")

    split: Split[Window[FlowRecord]]
    if args.split_policy == "family-holdout":
        if not args.holdout_family:
            print("family-holdout needs --holdout-family", file=sys.stderr)
            return 1
        split = family_split(windows, holdout=args.holdout_family)
    elif args.split_policy == "entity-only":
        split = group_split(windows)
    else:
        split = split_windows(
            windows, entity_disjoint=args.split_policy != "temporal-only"
        )
    print(f"  split {args.split_policy}: {split.audit()}")

    preprocessor = _fit(split.train, key)

    # T-203 is a release blocker, so it runs on the real artifacts and not on a
    # description of them: the scaler actually fitted above is recomputed from the
    # training fold and compared. A run that leaks exits non-zero rather than
    # producing a metric that describes the leak.
    audit_train_rows = [
        list(feature.numeric)
        for window in split.train
        for feature in extract_flow_window(window.records, key=key)
    ]
    audit = audit_trained(
        split, preprocessor.scaler, audit_train_rows, fit_on=split.train
    )
    blockers = blocking_findings(audit, split)
    declared = [f for f in audit.findings if f not in blockers]
    for finding in declared:
        print(f"  leakage audit: declared by this policy, not blocking - {finding}")
    if blockers:
        for finding in blockers:
            print(f"leakage audit: {finding}", file=sys.stderr)
        print(
            "refusing to train: the leakage audit failed (T-203, R-62)", file=sys.stderr
        )
        return 1
    print("  leakage audit: no blocking findings (T-203)")
    train_seq, train_y, _ = _sequences(split.train, key, preprocessor, 50)
    test_seq, test_y, _ = _sequences(split.test, key, preprocessor, 50)
    if not train_seq or not test_seq:
        print("a fold came out empty", file=sys.stderr)
        return 1
    print(f"  {len(train_seq):,} train / {len(test_seq):,} test windows")

    config = TrainingConfig(
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        seed=args.seed,
    )
    digest = DatasetDigest.of(path)
    sha, dirty = git_state()
    out_dir = (
        args.out_dir
        if os.path.isabs(args.out_dir)
        else os.path.join(ROOT, args.out_dir)
    )
    os.makedirs(out_dir, exist_ok=True)

    aucs: list[float] = []
    for run in range(1, args.runs + 1):
        print(f"run {run}/{args.runs}: training {config.epochs} epochs")
        model, losses = train(config, train_seq, train_y)
        model.eval()
        with torch.no_grad():
            scores = torch.sigmoid(
                model(torch.tensor(test_seq, dtype=torch.float32)).anomaly_logits
            ).tolist()
        report = evaluate(
            [float(s) for s in scores],
            [bool(t) for t in test_y],
            model_id=config.model_id,
        )
        auc = float(report.metrics.roc_auc)
        aucs.append(auc)
        manifest = RunManifest(
            model_id=config.model_id,
            git_sha=sha,
            git_dirty=dirty,
            config=config,
            seeds=seed_map(config.seed),
            datasets=(digest,),
            metrics=json.loads(report.model_dump_json()),
            environment={
                "python": sys.version.split()[0],
                "torch": torch.__version__,
                "split_policy": args.split_policy,
                "holdout_family": ",".join(args.holdout_family or []),
            },
        )
        manifest.save(os.path.join(out_dir, f"manifest_run{run}.json"))
        print(f"  final loss {losses[-1]:.5f}  ROC-AUC {auc:.6f}")

    spread = max(aucs) - min(aucs)
    passed = spread <= AUC_TOLERANCE
    print(
        f"AUC spread across {len(aucs)} runs: {spread:.6f} "
        f"(tolerance ±{AUC_TOLERANCE}): {'PASS' if passed else 'FAIL'}"
    )
    if dirty:
        print(
            "warning: git_dirty is true, so these manifests are not "
            "reproducible from the SHA alone"
        )
    summary = {
        "task": "T-202",
        "runs": len(aucs),
        "aucs": aucs,
        "auc_spread": spread,
        "tolerance": AUC_TOLERANCE,
        "passed": passed,
        "git_sha": sha,
        "git_dirty": dirty,
        "dataset_sha256": digest.sha256,
        "leakage_audit": {
            "blocking": [str(f) for f in blockers],
            "declared_by_policy": [str(f) for f in declared],
        },
    }
    with open(
        os.path.join(out_dir, "reproducibility.json"), "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")
    print(f"wrote {out_dir}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
