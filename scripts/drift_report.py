#!/usr/bin/env python
r"""Per-feature drift between two corpora (T-211, FR-32).

    python scripts/drift_report.py \
        --reference unsw_nb15_official_schema_sample.csv --reference-dataset unsw-nb15 \
        --actual Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv \
        --actual-dataset cic-ids2017 --out data/runs/drift_unsw_to_cic.json

Drift is a signal, not a failure, so this exits 0 when drift is found — a monitor
that fails the build every time traffic legitimately changes would be switched
off. ``--fail-on-drift`` turns it into a gate for the cases where a release must
not ship against a shifted distribution.

Run against UNSW-NB15 as the reference and CIC-IDS2017 as the incoming corpus this
is the measurement behind T-208: it names *which* features moved, which is what a
recall number on its own cannot tell you.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml-service"))
sys.path.insert(0, ROOT)

from aegis_ml.data.features import (  # noqa: E402
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    extract_flow_window,
)
from aegis_ml.data.windowing import WindowKey, window_flows  # noqa: E402
from aegis_ml.scoring.drift import (  # noqa: E402
    PSI_DRIFT_THRESHOLD,
    InMemoryMetricSink,
    measure_drift,
)

from scripts.train_flownet import PARSERS  # noqa: E402


def _columns(
    path: str, dataset: str, key: WindowKey, max_rows: int
) -> dict[str, list[object]]:
    """Parse one corpus and return one column per feature."""
    resolved = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.isfile(resolved):
        resolved = os.path.join(ROOT, "data", "raw", os.path.basename(path))
    print(f"reading {resolved}")
    parsed = PARSERS[dataset](resolved)
    parsed.report.raise_for_empty()

    columns: dict[str, list[object]] = {name: [] for name in NUMERIC_FEATURES}
    for name in CATEGORICAL_FEATURES:
        columns[name] = []

    records = sorted(parsed.records, key=lambda record: record.timestamp)[:max_rows]
    # extract_flow_window covers exactly one entity, so the records have to be
    # grouped into per-entity windows first rather than fed in as one stream.
    windows = window_flows(records, key=key)
    rows = [
        row
        for window in windows
        for row in extract_flow_window(window.records, key=key)
    ]
    print(
        f"  {parsed.report.parsed:,} rows parsed -> {len(windows):,} windows, "
        f"{len(rows):,} feature rows used"
    )
    for row in rows:
        for index, name in enumerate(NUMERIC_FEATURES):
            columns[name].append(float(row.numeric[index]))
        for index, name in enumerate(CATEGORICAL_FEATURES):
            columns[name].append(str(row.categorical[index]))
    return columns


def main(argv: list[str] | None = None) -> int:
    """Compute per-feature PSI between a reference and an incoming corpus."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference", required=True)
    parser.add_argument(
        "--reference-dataset", choices=sorted(PARSERS), default="unsw-nb15"
    )
    parser.add_argument("--actual", required=True)
    parser.add_argument(
        "--actual-dataset", choices=sorted(PARSERS), default="cic-ids2017"
    )
    parser.add_argument("--key", choices=("source", "destination"), default="source")
    parser.add_argument("--max-rows", type=int, default=20000)
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=PSI_DRIFT_THRESHOLD)
    parser.add_argument("--fail-on-drift", action="store_true")
    parser.add_argument("--out", default="data/runs/drift.json")
    args = parser.parse_args(argv)

    key = WindowKey.SOURCE if args.key == "source" else WindowKey.DESTINATION
    reference = _columns(args.reference, args.reference_dataset, key, args.max_rows)
    actual = _columns(args.actual, args.actual_dataset, key, args.max_rows)

    sink = InMemoryMetricSink()
    report = measure_drift(
        reference, actual, bins=args.bins, threshold=args.threshold, sink=sink
    )

    ordered = sorted(report.features, key=lambda entry: -entry.psi)
    print(
        f"per-feature PSI, worst first (threshold {args.threshold}, "
        f"metric aegis_drift_psi{{feature}}):"
    )
    for entry in ordered:
        marker = "DRIFT" if entry.drifted else "     "
        print(
            f"  {marker} {entry.feature:22s} psi {entry.psi:8.4f}  {entry.band:12s} "
            f"({entry.bins} bins)"
        )
    print(
        f"{len(report.drifted())} of {len(report.features)} features over "
        f"{args.threshold}: {'DRIFT DETECTED' if report.any_drift else 'no drift'}"
    )
    print(f"{len(sink.records)} aegis_drift_psi readings published")

    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "task": "T-211",
                "rule": "FR-32",
                "reference": args.reference,
                "actual": args.actual,
                "max_rows": args.max_rows,
                "bins": args.bins,
                "published_readings": len(sink.records),
                **report.as_json(),
            },
            handle,
            indent=2,
        )
        handle.write("\n")
    print(f"wrote {out}")
    return 1 if (args.fail_on_drift and report.any_drift) else 0


if __name__ == "__main__":
    raise SystemExit(main())
