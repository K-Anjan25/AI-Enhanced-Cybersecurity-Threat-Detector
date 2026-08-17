#!/usr/bin/env python
"""CLI trainer — thin wrapper over ``app.training.run_training``.

Runs a retrain from the CICIDS datasets when available. The log/email models
always train (built-in corpora); the network IsolationForest needs
``datasets/CICIDS2017/*.csv`` and is skipped unless ``--require-network`` is set.
Used both interactively and as a Docker build-time bake-in step.

Usage (from ml-service/):
    python train.py                       # network skipped if data absent
    python train.py --require-network      # fail loudly if dataset missing
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.training import run_training  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Threat AI ML models.")
    parser.add_argument(
        "--require-network",
        action="store_true",
        help="Fail if the CICIDS2017 dataset is missing (default: skip network model).",
    )
    args = parser.parse_args()

    manifest = run_training(require_network=args.require_network)
    print("All models processed.")
    print(f"Version: {manifest['version']}")
    for entry in manifest["models"]:
        print(f"  - {entry['model']}: {entry['status']}")


if __name__ == "__main__":
    main()