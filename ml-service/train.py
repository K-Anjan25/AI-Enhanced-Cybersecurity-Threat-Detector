#!/usr/bin/env python
"""CLI trainer — thin wrapper over ``app.training.run_training``.

Runs a full retrain from the CICIDS datasets (log/email models train from their
built-in corpora; the network IsolationForest needs ``datasets/CICIDS2017/*.csv``).
Equivalent behavior to the original monolithic script, now shared with the
in-service ``POST /retrain`` endpoint.

Usage (from ml-service/):  python train.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.training import run_training  # noqa: E402


def main() -> None:
    manifest = run_training(require_network=True)
    print("All models trained and saved.")
    print(f"Version: {manifest['version']}")
    for entry in manifest["models"]:
        print(f"  - {entry['model']}: {entry['status']}")


if __name__ == "__main__":
    main()