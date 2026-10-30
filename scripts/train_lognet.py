#!/usr/bin/env python
r"""Train LogNet on a labelled BGL log file and write a serving bundle.

    python scripts/train_lognet.py \
        --raw ~/aegis-data/loghub/BGL/BGL_2k.log \
        --structured ~/aegis-data/loghub/BGL/BGL_2k.log_structured.csv \
        --out data/runs/lognet-bgl-2k

The raw file gives the messages and the template mining; the structured CSV gives the
labels (``Label`` is ``-`` for normal lines). The two must describe the same lines in
the same order, and this script checks that by comparing timestamps before training.

The metrics are printed as JSON and stored in the bundle. With a small corpus they
are reported as they are, with their window counts; they are not a claim of accuracy.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml-service"))

from aegis_ml.data.log_parsers import parse_bgl  # noqa: E402
from aegis_ml.training.lognet_train import (  # noqa: E402
    LogLine,
    LogNetTrainConfig,
    train_bundle,
)


def read_labelled_lines(raw: Path, structured: Path) -> list[LogLine]:
    """Pair each parsed line with its label, after checking the two files agree."""
    parsed = parse_bgl(str(raw))
    with structured.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != len(parsed.records):
        raise SystemExit(
            f"line count mismatch: {len(parsed.records)} parsed from {raw.name}, "
            f"{len(rows)} rows in {structured.name}"
        )
    lines: list[LogLine] = []
    for record, row in zip(parsed.records, rows, strict=True):
        epoch = float(row["Timestamp"])
        if int(record.timestamp.timestamp()) != int(epoch):
            raise SystemExit(
                f"timestamp mismatch at LineId {row['LineId']}: the raw and structured "
                "files are not the same log"
            )
        lines.append(
            LogLine(
                epoch=epoch,
                message=record.message,
                anomalous=row["Label"] != "-",
                flagged=record.level.value != "info",
            )
        )
    return lines


def main() -> None:
    """Parse arguments, train, print the metrics, and write the bundle."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--raw", type=Path, required=True, help="BGL raw log file")
    parser.add_argument("--structured", type=Path, required=True, help="BGL structured CSV")
    parser.add_argument("--out", type=Path, required=True, help="bundle output directory")
    parser.add_argument("--epochs", type=int, default=LogNetTrainConfig.epochs)
    parser.add_argument("--window", type=int, default=LogNetTrainConfig.window)
    parser.add_argument("--stride", type=int, default=LogNetTrainConfig.stride)
    parser.add_argument("--seed", type=int, default=LogNetTrainConfig.seed)
    args = parser.parse_args()

    lines = read_labelled_lines(args.raw, args.structured)
    cfg = LogNetTrainConfig(
        window=args.window, stride=args.stride, epochs=args.epochs, seed=args.seed
    )
    metrics = train_bundle(lines, args.out, cfg)
    print(json.dumps({"out": os.fspath(args.out), "metrics": metrics}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
