#!/usr/bin/env python
r"""Train, track, register, gate, promote and roll back LogNet with MLflow.

    python scripts/lognet_lifecycle.py train \
        --raw ~/aegis-data/loghub/BGL/BGL_2k.log \
        --structured ~/aegis-data/loghub/BGL/BGL_2k.log_structured.csv
    python scripts/lognet_lifecycle.py status
    python scripts/lognet_lifecycle.py promote 1
    python scripts/lognet_lifecycle.py rollback

``train`` logs the run and registers it as a new version. It promotes only when
``--promote`` is given and the gate passes. Gate failures are printed with their
reasons and exit non-zero, so a script can tell them apart from crashes.

Tracking lives in ``~/.aegis/mlflow`` unless ``AEGIS_MLFLOW_DIR`` or
``AEGIS_MLFLOW_TRACKING_URI`` says otherwise. Nothing is written inside the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml-service"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aegis_ml.lifecycle import mlflow_lifecycle as lc  # noqa: E402
from aegis_ml.training.lognet_train import (  # noqa: E402
    LogNetTrainConfig,
    digest_lines,
    train_bundle,
)
from train_lognet import read_labelled_lines  # noqa: E402

EXIT_GATE_REFUSED = 3


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def cmd_train(args: argparse.Namespace) -> int:
    """Train, log the run, register it, and optionally promote if the gate passes."""
    lines = read_labelled_lines(args.raw, args.structured)
    data_sha = digest_lines(lines)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or lc.store_dir() / "runs" / stamp
    cfg = LogNetTrainConfig(
        window=args.window, stride=args.stride, epochs=args.epochs, seed=args.seed
    )
    train_bundle(lines, out, cfg)
    mlf = lc.client()
    run = lc.log_run(mlf, out, experiment=args.experiment, data_sha256=data_sha)
    version = lc.register_version(mlf, run, data_sha256=data_sha)
    gate = lc.evaluate_gate(run.metrics, lc.GateConfig(min_roc_auc=args.min_auc))
    result: dict[str, Any] = {
        "run_id": run.run_id,
        "version": version,
        "bundle": str(out),
        "metrics": run.metrics,
        "gate": json.loads(gate.as_tag()),
        "promoted": False,
    }
    if args.promote:
        try:
            replaced = lc.promote(mlf, version, gate, download_dir=out / ".verify")
        except lc.GateRefused as refusal:
            result["promotion"] = str(refusal)
            _emit(result)
            return EXIT_GATE_REFUSED
        result["promoted"] = True
        result["replaced_version"] = replaced
    _emit(result)
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    """Promote an existing version, judged by the gate on its stored run metrics."""
    mlf = lc.client()
    version = mlf.get_model_version(lc.MODEL_NAME, str(args.version))
    metrics = mlf.get_run(version.run_id).data.metrics
    gate = lc.evaluate_gate(metrics, lc.GateConfig(min_roc_auc=args.min_auc))
    try:
        replaced = lc.promote(mlf, str(args.version), gate, download_dir=lc.store_dir() / ".verify")
    except lc.GateRefused as refusal:
        _emit(
            {"version": args.version, "promotion": str(refusal), "gate": json.loads(gate.as_tag())}
        )
        return EXIT_GATE_REFUSED
    _emit({"version": args.version, "promoted": True, "replaced_version": replaced})
    return 0


def cmd_rollback(_: argparse.Namespace) -> int:
    """Return the champion alias to the version it replaced."""
    mlf = lc.client()
    restored = lc.rollback(mlf, download_dir=lc.store_dir() / ".verify")
    _emit({"champion": restored})
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    """Show the champion and every version with its gate decision."""
    mlf = lc.client()
    current = lc.champion(mlf)
    versions = []
    listed = mlf.search_model_versions(f"name='{lc.MODEL_NAME}'")
    for version in sorted(listed, key=lambda v: int(v.version)):
        versions.append(
            {
                "version": version.version,
                "run_id": version.run_id,
                "previous": version.tags.get(lc.PREVIOUS_TAG, ""),
                "gate": version.tags.get(lc.GATE_TAG, ""),
                "rolled_back_at": version.tags.get(lc.ROLLED_BACK_TAG, ""),
            }
        )
    _emit(
        {
            "tracking_uri": lc.tracking_uri(),
            "champion": None if current is None else current.version,
            "versions": versions,
        }
    )
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """Download the champion bundle, verified, and print the directory to serve from."""
    bundle = lc.fetch_champion(lc.client(), args.dest)
    _emit({"bundle_dir": str(bundle), "serve_with": f"AEGIS_LOGNET_BUNDLE_DIR={bundle}"})
    return 0


def main() -> int:
    """Dispatch the subcommand."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="train, log, register; promote with --promote")
    train.add_argument("--raw", type=Path, required=True)
    train.add_argument("--structured", type=Path, required=True)
    train.add_argument("--out", type=Path, default=None, help="bundle directory")
    train.add_argument("--experiment", default="lognet")
    train.add_argument("--epochs", type=int, default=LogNetTrainConfig.epochs)
    train.add_argument("--window", type=int, default=LogNetTrainConfig.window)
    train.add_argument("--stride", type=int, default=LogNetTrainConfig.stride)
    train.add_argument("--seed", type=int, default=LogNetTrainConfig.seed)
    train.add_argument("--min-auc", type=float, default=lc.GateConfig.min_roc_auc)
    train.add_argument("--promote", action="store_true")
    train.set_defaults(func=cmd_train)

    promote = sub.add_parser("promote", help="promote a version if it passes the gate")
    promote.add_argument("version", type=int)
    promote.add_argument("--min-auc", type=float, default=lc.GateConfig.min_roc_auc)
    promote.set_defaults(func=cmd_promote)

    rollback = sub.add_parser("rollback", help="return champion to the version it replaced")
    rollback.set_defaults(func=cmd_rollback)

    fetch = sub.add_parser("fetch", help="download the verified champion bundle for serving")
    fetch.add_argument("--dest", type=Path, default=lc.store_dir() / "serving")
    fetch.set_defaults(func=cmd_fetch)

    status = sub.add_parser("status", help="show champion and version history")
    status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    try:
        return int(args.func(args))
    except lc.LifecycleError as refusal:
        # A refusal is an expected outcome with a stated reason, not a crash.
        _emit({"refused": type(refusal).__name__, "reason": str(refusal)})
        return EXIT_GATE_REFUSED if isinstance(refusal, lc.GateRefused) else 2


if __name__ == "__main__":
    raise SystemExit(main())
