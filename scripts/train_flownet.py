#!/usr/bin/env python
r"""Train ``FlowNet`` on flow windows (T-201).

    python scripts/train_flownet.py --synthetic 4000 --epochs 3 --out out.json
    python scripts/train_flownet.py --records data/clean/cic_friday.ndjson \\
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml-service"))

from aegis_ml.data.features import (  # noqa: E402
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    FlowFeatures,
    extract_flow_window,
)
from aegis_ml.data.preprocess import (  # noqa: E402
    Preprocessor,
    StandardScaler,
    Vocabulary,
)
from aegis_ml.data.records import FlowRecord  # noqa: E402
from aegis_ml.data.splits import Split, split_windows  # noqa: E402
from aegis_ml.data.synthetic import generate_dataset  # noqa: E402
from aegis_ml.data.windowing import Window, WindowKey, window_flows  # noqa: E402
from aegis_ml.training.baselines import design_matrix  # noqa: E402
from aegis_ml.training.evaluation import EvalReport, evaluate  # noqa: E402

DEFAULT_SEED = 20260114
ACCEPTANCE_MINUTES = 10.0


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
        # A window has no label of its own: it is an attack if any flow in it is
        # one. design_matrix has already dropped unlabelled rows, so a window
        # that yields no rows is unusable rather than silently benign.
        if not targets:
            continue
        sequences.append(matrix)
        labels.append(1 if any(targets) else 0)
    return sequences, labels, padded


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, train FlowNet, and write the run log."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--records", help="path to cleaned flow records (NDJSON)")
    source.add_argument(
        "--synthetic", type=int, metavar="N", help="generate N synthetic records"
    )
    parser.add_argument(
        "--dataset", default="synthetic", help="dataset name, for the run log"
    )
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
    if args.synthetic:
        print(f"generating {args.synthetic:,} records per scenario (seed {args.seed})")
        records = list(
            generate_dataset(per_scenario=args.synthetic, seed=args.seed).flows
        )
    else:
        records = list(_load_records(args.records))
    if not records:
        print("no records to train on", file=sys.stderr)
        return 1

    records.sort(
        key=lambda record: record.timestamp
    )  # window_flows needs arrival order
    windows = window_flows(records, key=key)
    print(f"{len(records):,} records -> {len(windows):,} windows keyed by {key.value}")

    split: Split[Window[FlowRecord]] = split_windows(windows, entity_disjoint=True)
    audit = split.audit()
    print(f"split: {audit}")
    if not audit["test_after_train"]:
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
        "source": f"synthetic:{args.synthetic}" if args.synthetic else args.records,
        "window_key": key.value,
        "windows": len(windows),
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
        "acceptance": {
            "criterion": "end-to-end training on a 1% sample in under 10 minutes on CPU",
            "budget_minutes": ACCEPTANCE_MINUTES,
            "passed": bool(minutes < ACCEPTANCE_MINUTES),
        },
        "report": json.loads(report.model_dump_json()),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(log, handle, indent=2)
        handle.write("\n")

    print(f"training took {minutes:.3f} minutes (budget {ACCEPTANCE_MINUTES})")
    print(
        f"ROC-AUC {report.roc_auc:.4f}  PR-AUC {report.pr_auc:.4f}  best F1 {report.best_f1:.4f}"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
