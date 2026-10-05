#!/usr/bin/env python
r"""Train ``FlowNet`` on flow windows (T-201).

    python scripts/train_flownet.py --synthetic 4000 --epochs 3 --out out.json
    python scripts/train_flownet.py --file data/raw/Friday-DDos.csv \\
        --dataset cic-ids2017 --sample-frac 0.01 --epochs 3 --out out.json

T-201's acceptance criterion is a wall-clock one — end-to-end training on a 1%
sample in under ten minutes on a CPU — so this script measures and reports that
directly rather than leaving it to be inferred.

The unit of training is a *window*, not a flow. ``features@1`` yields one row
per flow, so a window becomes a sequence of up to ``FLOW_WINDOW_SIZE`` rows; the
transformer sees the ordering, which is where beaconing and slow exfiltration
live. Shorter windows are padded with zeros *after* standardisation, which makes
a pad equal the training mean rather than an arbitrary constant.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from dataclasses import replace

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
from aegis_ml.data.splits import (  # noqa: E402
    family_split,
    group_split,
    split_windows,
    window_families,
)
from aegis_ml.data.synthetic import generate_dataset  # noqa: E402
from aegis_ml.data.windowing import Window, WindowKey, window_flows  # noqa: E402
from aegis_ml.training.baselines import design_matrix  # noqa: E402
from aegis_ml.training.evaluation import EvalReport, evaluate  # noqa: E402

PARSERS = {
    "cic-ids2017": parse_cic_ids2017,
    "unsw-nb15": parse_unsw_nb15,
}

DEFAULT_SEED = 20260114
ACCEPTANCE_MINUTES = 10.0
#: T-201's second acceptance clause: parameter count within 20% of this target.
PARAMETER_TARGET = 1_200_000


def _load_records(path: str) -> list[FlowRecord]:
    """Read cleaned flow records from NDJSON."""
    records: list[FlowRecord] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(FlowRecord.model_validate_json(line))
    return records


def _fit(windows: Sequence[Window[FlowRecord]], key: WindowKey) -> Preprocessor:
    """Fit the scaler and vocabularies on the training windows alone (R-62)."""
    rows: list[FlowFeatures] = []
    for window in windows:
        rows.extend(extract_flow_window(window.records, key=key))
    scaler = StandardScaler.fit([list(r.numeric) for r in rows], NUMERIC_FEATURES)
    vocabularies = {
        name: Vocabulary.fit(r.categorical[index] for r in rows)
        for index, name in enumerate(CATEGORICAL_FEATURES)
    }
    return Preprocessor(scaler=scaler, vocabularies=vocabularies)


def _sequences(
    windows: Sequence[Window[FlowRecord]],
    key: WindowKey,
    preprocessor: Preprocessor,
    length: int,
) -> tuple[list[list[list[float]]], list[int], int]:
    """Turn windows into padded ``(seq, features)`` matrices.

    Returns the sequences, the window labels, and how many windows were padded.
    """
    sequences: list[list[list[float]]] = []
    labels: list[int] = []
    padded = 0
    for window in windows:
        rows = extract_flow_window(window.records, key=key)
        # features@1 deliberately labels a window None when its member flows
        # disagree, so multi-class training never sees an ambiguous target. That
        # is the right call for multi-class and the wrong one here: a window
        # holding Fuzzers and Generic traffic is ambiguous as a *family* and
        # unambiguous as an *attack*. design_matrix is already binary, so the
        # rows are relabelled to the binary target rather than being dropped.
        # On the UNSW-NB15 sample the old path silently discarded every one of
        # the 21 attack windows in the test fold and kept 34 benign ones.
        families = window_families(window)
        binary = "normal" if not families else "attack"
        rows = [replace(row, label=binary) for row in rows]
        matrix, targets = design_matrix(rows, preprocessor)
        if not matrix:
            continue
        if len(matrix) < length:
            # Zeros in standardised space are the training mean, so padding does
            # not introduce a value the encoder has never seen.
            matrix = matrix + [[0.0] * len(matrix[0])] * (length - len(matrix))
            padded += 1
        elif len(matrix) > length:
            matrix = matrix[:length]
        sequences.append(matrix)
        labels.append(1 if any(targets) else 0)
    return sequences, labels, padded


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, train FlowNet, and write the run log."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--file",
        action="append",
        help="Input file under data/. Repeatable to combine capture days.",
    )
    source.add_argument(
        "--synthetic", type=int, metavar="N", help="generate N records per scenario"
    )
    parser.add_argument(
        "--format",
        choices=["csv", "ndjson"],
        default="csv",
        help="csv for a fetched dataset, ndjson for flow@1 records.",
    )
    parser.add_argument("--dataset", choices=sorted(PARSERS), default="cic-ids2017")
    parser.add_argument(
        "--key",
        choices=("source", "destination"),
        default="source",
        help="entity dimension a window is keyed on (D-013)",
    )
    parser.add_argument("--out", required=True, help="where to write the run log")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--split-policy",
        choices=("entity-disjoint", "temporal-only", "entity-only", "family-holdout"),
        default="entity-disjoint",
        help=(
            "temporal = chronological and entity-disjoint (R-60/R-61). "
            "entity-only = whole entities by hash, temporal invariant dropped. "
            "Use entity-only on synthetic data, whose classes have disjoint time "
            "ranges by construction (D-017)."
        ),
    )
    parser.add_argument(
        "--holdout-family",
        action="append",
        help=(
            "Attack family to withhold from training, for --split-policy "
            "family-holdout. Repeatable. Required by that policy."
        ),
    )
    parser.add_argument(
        "--sample-frac",
        type=float,
        default=1.0,
        help="fraction of TRAINING windows to use; 0.01 is the acceptance run",
    )
    args = parser.parse_args(argv)

    import torch  # noqa: PLC0415  (optional extra; import only once argparse is done)
    from aegis_ml.models.flownet import (  # noqa: PLC0415
        FlowNet,
        FlowNetConfig,
        parameter_count,
        reconstruction_error,
    )

    key = WindowKey.SOURCE if args.key == "source" else WindowKey.DESTINATION
    reports: list[ParseReport] = []
    if args.synthetic:
        print(f"generating {args.synthetic:,} records per scenario (seed {args.seed})")
        records = list(
            generate_dataset(per_scenario=args.synthetic, seed=args.seed).flows
        )
    else:
        records = []
        for raw in args.file:
            path = raw if os.path.isabs(raw) else os.path.join(ROOT, raw)
            if not os.path.isfile(path):
                path = os.path.join(ROOT, "data", "raw", os.path.basename(raw))
            print(f"reading {path}")
            if args.format == "ndjson":
                records.extend(_load_records(path))
            else:
                parsed = PARSERS[args.dataset](path)
                parsed.report.raise_for_empty()
                reports.append(parsed.report)
                print(
                    f"  {parsed.report.parsed:,} of {parsed.report.rows_read:,} rows "
                    f"parsed ({parsed.report.rejected:,} rejected)"
                )
                records.extend(parsed.records)
        print(f"  combined: {len(records):,} records")
    if not records:
        print("no records to train on", file=sys.stderr)
        return 1

    records.sort(
        key=lambda record: record.timestamp
    )  # window_flows needs arrival order
    windows = window_flows(records, key=key)
    print(f"{len(records):,} records -> {len(windows):,} windows keyed by {key.value}")

    entity_only = args.split_policy == "entity-only"
    entity_disjoint = args.split_policy not in ("temporal-only", "family-holdout")
    if args.split_policy == "family-holdout":
        if not args.holdout_family:
            print(
                "family-holdout needs --holdout-family to name what to withhold",
                file=sys.stderr,
            )
            return 1
        split = family_split(windows, holdout=args.holdout_family)
    elif entity_only:
        split = group_split(windows)
    else:
        split = split_windows(windows, entity_disjoint=entity_disjoint)
    audit = split.audit()
    print(f"split policy: {args.split_policy}")
    print(f"split: {audit}")
    # entity-only drops the temporal invariant by design and says so, rather than
    # being allowed to fail it silently.
    if args.split_policy == "family-holdout":
        print(
            f"warning: holding out {sorted(args.holdout_family)}; the model has never "
            "seen this family. Neither leakage invariant is enforced, because the "
            "thing held out is the attack type, not the host - read the audit",
            file=sys.stderr,
        )
    elif entity_only:
        print(
            "warning: entity-only does NOT enforce the temporal invariant (R-60); "
            "these metrics are not comparable to a production-style split",
            file=sys.stderr,
        )
    elif not entity_disjoint:
        print(
            "warning: temporal-only lets entities span folds, so the measured "
            f"leakage is {audit['shared_train_test_entities']} shared entities; "
            "comparable to published benchmarks, not to a released model",
            file=sys.stderr,
        )
        if not audit["test_after_train"]:
            print(
                "refusing to train: the split violates the temporal invariant (R-60)",
                file=sys.stderr,
            )
            return 1
    elif not audit["test_after_train"]:
        print(
            "refusing to train: the split violates the temporal invariant (R-60)",
            file=sys.stderr,
        )
        return 1
    if not split.test:
        print("refusing to train: the test fold is empty", file=sys.stderr)
        return 1

    preprocessor = _fit(split.train, key)
    train_seq, train_y, _ = _sequences(split.train, key, preprocessor, 50)
    test_seq, test_y, padded = _sequences(split.test, key, preprocessor, 50)

    if 0.0 < args.sample_frac < 1.0:
        # A stride, not a draw, so two runs train on the same windows (R-67).
        stride = max(1, round(1.0 / args.sample_frac))
        train_seq, train_y = train_seq[::stride], train_y[::stride]
        print(f"sampled 1/{stride} of the training windows for the acceptance run")
    if not train_seq:
        print("no training windows left after sampling", file=sys.stderr)
        return 1

    # design_matrix one-hot encodes the categoricals, so the width the encoder
    # sees is wider than the raw feature vector. Take it from the data rather
    # than assuming, or the two will drift apart silently.
    width = len(train_seq[0][0])
    torch.manual_seed(args.seed)
    model = FlowNet(FlowNetConfig(input_dim=width))
    params = parameter_count(model)
    print(
        f"FlowNet: {params:,} parameters over {width} input columns; "
        f"{len(train_seq):,} train / {len(test_seq):,} test windows"
    )

    x_train = torch.tensor(train_seq, dtype=torch.float32)
    y_train = torch.tensor(train_y, dtype=torch.float32)
    optimiser = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    bce = torch.nn.BCEWithLogitsLoss()

    print(f"training {args.epochs} epochs on CPU")
    started = time.perf_counter()
    model.train()
    for epoch in range(args.epochs):
        order = torch.randperm(
            x_train.size(0), generator=torch.Generator().manual_seed(args.seed + epoch)
        )
        total, batches = 0.0, 0
        for start in range(0, order.numel(), args.batch_size):
            index = order[start : start + args.batch_size]
            x, y = x_train[index], y_train[index]
            optimiser.zero_grad()
            output = model(x)
            loss = reconstruction_error(output, x) + bce(output.anomaly_logits, y)
            loss.backward()
            optimiser.step()
            total += float(loss.item())
            batches += 1
        print(f"  epoch {epoch + 1}/{args.epochs}  loss {total / batches:.5f}")
    elapsed = time.perf_counter() - started

    model.eval()
    x_test = torch.tensor(test_seq, dtype=torch.float32)
    with torch.no_grad():
        scores = torch.sigmoid(model(x_test).anomaly_logits).tolist()
    report: EvalReport = evaluate(
        [float(s) for s in scores],
        [bool(t) for t in test_y],
        model_id="flownet-v0.1.0",
    )

    minutes = elapsed / 60.0
    log: dict[str, object] = {
        "task": "T-201",
        "model_id": "flownet-v0.1.0",
        "source": f"synthetic:{args.synthetic}" if args.synthetic else list(args.file),
        "parse_rejected": sum(r.rejected for r in reports),
        "window_key": key.value,
        "windows": len(windows),
        "split_policy": args.split_policy,
        "holdout_family": list(args.holdout_family or []),
        "split_audit": audit,
        "train_windows": len(train_seq),
        "test_windows": len(test_seq),
        "padded_test_windows": padded,
        "sample_frac": args.sample_frac,
        "input_dim": width,
        "parameters": params,
        "epochs": args.epochs,
        "torch": torch.__version__,
        "train_seconds": round(elapsed, 3),
        "train_minutes": round(minutes, 3),
        # T-201 has two acceptance clauses and a run log that records one of them
        # invites reading it as a pass on both.
        "acceptance": {
            "wall_clock": {
                "criterion": "trains end to end on a 1% sample in under 10 min on CPU",
                "budget_minutes": ACCEPTANCE_MINUTES,
                "actual_minutes": round(minutes, 4),
                "passed": bool(minutes < ACCEPTANCE_MINUTES),
            },
            "size": {
                "criterion": "parameter count within 20% of the 1.2M target",
                "target_parameters": PARAMETER_TARGET,
                "band": [int(PARAMETER_TARGET * 0.8), int(PARAMETER_TARGET * 1.2)],
                "actual_parameters": params,
                "passed": bool(
                    0.8 * PARAMETER_TARGET <= params <= 1.2 * PARAMETER_TARGET
                ),
            },
        },
        "report": json.loads(report.model_dump_json()),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(log, handle, indent=2)
        handle.write("\n")

    print(f"training took {minutes:.3f} minutes (budget {ACCEPTANCE_MINUTES})")
    band = (int(PARAMETER_TARGET * 0.8), int(PARAMETER_TARGET * 1.2))
    print(
        f"parameters {params:,} against a {PARAMETER_TARGET:,} target "
        f"(band {band[0]:,}-{band[1]:,}): "
        f"{'within' if band[0] <= params <= band[1] else 'OUTSIDE'}"
    )
    print(
        f"test fold: {report.positives:,} attack / {report.negatives:,} benign windows"
    )
    print(
        f"ROC-AUC {report.metrics.roc_auc:.4f}  "
        f"PR-AUC {report.metrics.pr_auc:.4f}  "
        f"best F1 {report.best_f1.f1:.4f} @ threshold {report.best_f1.threshold:.2f}"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
