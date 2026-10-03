#!/usr/bin/env python3
"""Generate synthetic telemetry as NDJSON (T-106).

Writes into data/ which is gitignored — generated data is never committed (R-40).

    python scripts/generate_synthetic.py --per-scenario 500 --seed 7
    python scripts/generate_synthetic.py --scenario port_scan --count 100 -o /tmp/scan.ndjson
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml-service"))

from aegis_ml.data.synthetic import (  # noqa: E402 - path configured above
    LOG_SCENARIOS,
    GenerationSpec,
    Scenario,
    generate_dataset,
    generate_flows,
    generate_logs,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--per-scenario",
        type=int,
        default=500,
        help="records per scenario (default 500)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="RNG seed; same seed, same output (default 7)",
    )
    parser.add_argument(
        "--scenario",
        choices=[s.value for s in Scenario],
        help="generate a single scenario instead of the full balanced set",
    )
    parser.add_argument(
        "--count",
        type=int,
        help="record count when --scenario is given (defaults to --per-scenario)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "data" / "synthetic"),
        help="output directory",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Generate and write the dataset. Returns a process exit code."""
    args = parse_args(argv)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.scenario is not None:
        scenario = Scenario(args.scenario)
        one = GenerationSpec(
            scenario=scenario, count=args.count or args.per_scenario, seed=args.seed
        )
        flows = generate_flows(one)
        targets: list[tuple[Path, Any]] = [
            (
                out_dir / f"flows_{scenario.value}.ndjson",
                (r.model_dump_json() for r in flows),
            )
        ]
        if scenario in LOG_SCENARIOS:
            logs = generate_logs(one)
            targets.append(
                (
                    out_dir / f"logs_{scenario.value}.ndjson",
                    (r.model_dump_json() for r in logs),
                )
            )
    else:
        dataset = generate_dataset(per_scenario=args.per_scenario, seed=args.seed)
        targets = [
            (out_dir / "flows.ndjson", (r.model_dump_json() for r in dataset.flows)),
            (out_dir / "logs.ndjson", (r.model_dump_json() for r in dataset.logs)),
        ]

    total = 0
    for path, lines in targets:
        written = 0
        with open(path, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")
                written += 1
        total += written
        print(f"wrote {written:6d} records -> {os.path.relpath(path, ROOT)}")

    print(f"total {total} records, seed={args.seed}")
    print(
        "reminder: data/ is gitignored; never commit generated or real telemetry (R-40)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
