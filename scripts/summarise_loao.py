"""Summarise leave-one-attacker-out run logs into one table.

Reads ``loao_baselines_<entity>.json`` (from run_baselines.py) and
``loao_flownet_<entity>.json`` (from train_flownet.py) and writes a Markdown table
and a CSV, one row per (held-out attacker, model).

Current logs carry a ``loao`` block: both models are scored per window with the
same any-attack labels, and the threshold is set on validation benign windows at
FPR <= 0.5% (PRD section 8). Those rows are the ones to quote.

Older logs without a ``loao`` block hold row-level baseline scores at a fixed 0.5
threshold. They are kept for reference and marked as such, because their test
sets differ from FlowNet's.

Usage:
    python scripts/summarise_loao.py --runs data/runs --out data/runs/loao_summary
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOAO_BASIS = "window, any-attack, threshold from validation benign at FPR<=0.5%"
LEGACY_BASIS = "row-level, fixed 0.5 (superseded)"


@dataclass(frozen=True)
class Row:
    """One held-out attacker scored by one model."""

    holdout: str
    model: str
    basis: str
    threshold: float
    positives: int
    negatives: int
    roc_auc: float
    pr_auc: float
    precision: float
    recall: float
    fpr: float
    tp: int
    fp: int
    fn: int
    tn: int
    high_precision: float | None
    high_recall: float | None

    def as_list(self) -> list[object]:
        """The row as table cells, in HEADER order."""
        return [
            self.holdout,
            self.model,
            self.basis,
            f"{self.threshold:.6f}",
            self.positives,
            self.negatives,
            f"{self.roc_auc:.4f}",
            f"{self.pr_auc:.4f}",
            f"{self.precision:.4f}",
            f"{self.recall:.4f}",
            f"{self.fpr:.4f}",
            self.tp,
            self.fp,
            self.fn,
            self.tn,
            "n/a" if self.high_precision is None else f"{self.high_precision:.4f}",
            "n/a" if self.high_recall is None else f"{self.high_recall:.4f}",
        ]


HEADER = [
    "held_out_attacker",
    "model",
    "scoring",
    "threshold",
    "test_positives",
    "test_negatives",
    "roc_auc",
    "pr_auc",
    "precision",
    "recall",
    "fpr",
    "tp",
    "fp",
    "fn",
    "tn",
    "precision@0.75",
    "recall@0.75",
]


def _rates(confusion: dict[str, int]) -> tuple[float, float, float]:
    tp, fp, fn, tn = (confusion[k] for k in ("tp", "fp", "fn", "tn"))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return precision, recall, fpr


def _loao_row(holdout: str, model: str, block: dict[str, Any]) -> Row:
    high = block["at_high"]
    return Row(
        holdout=holdout,
        model=model,
        basis=LOAO_BASIS,
        threshold=float(block["threshold"]),
        positives=int(block["test_positive_windows"]),
        negatives=int(block["test_negative_windows"]),
        roc_auc=float(block["roc_auc"]),
        pr_auc=float(block["pr_auc"]),
        precision=float(block["precision"]),
        recall=float(block["recall"]),
        fpr=float(block["fpr"]),
        tp=int(block["tp"]),
        fp=int(block["fp"]),
        fn=int(block["fn"]),
        tn=int(block["tn"]),
        high_precision=float(high["precision"]),
        high_recall=float(high["recall"]),
    )


def _legacy_row(
    holdout: str,
    model: str,
    positives: int,
    negatives: int,
    metrics: dict[str, float],
    confusion: dict[str, int],
) -> Row:
    precision, recall, fpr = _rates(confusion)
    return Row(
        holdout=holdout,
        model=model,
        basis=LEGACY_BASIS,
        threshold=0.5,
        positives=positives,
        negatives=negatives,
        roc_auc=metrics["roc_auc"],
        pr_auc=metrics["pr_auc"],
        precision=precision,
        recall=recall,
        fpr=fpr,
        tp=confusion["tp"],
        fp=confusion["fp"],
        fn=confusion["fn"],
        tn=confusion["tn"],
        high_precision=None,
        high_recall=None,
    )


def _baseline_rows(path: Path) -> list[Row]:
    data = json.loads(path.read_text(encoding="utf-8"))
    holdout = data["holdout_entity"]
    loao = data.get("loao") or {}
    if loao:
        return [_loao_row(holdout, model, block) for model, block in loao.items()]
    rows: list[Row] = []
    for model, body in data["models"].items():
        rows.append(
            _legacy_row(
                holdout,
                model,
                body["positives"],
                body["negatives"],
                body["metrics"],
                body["confusion"],
            )
        )
    return rows


def _flownet_row(path: Path) -> Row:
    data = json.loads(path.read_text(encoding="utf-8"))
    holdout = data["holdout_entity"]
    if data.get("loao"):
        return _loao_row(holdout, "flownet", data["loao"])
    report = data["report"]
    return _legacy_row(
        holdout,
        "flownet",
        report["positives"],
        report["negatives"],
        report["metrics"],
        report["confusion"],
    )


def collect(runs: Path) -> list[Row]:
    """Gather every LOAO run log in ``runs``, sorted by attacker then model."""
    rows: list[Row] = []
    for path in sorted(runs.glob("loao_baselines_*.json")):
        rows.extend(_baseline_rows(path))
    for path in sorted(runs.glob("loao_flownet_*.json")):
        rows.append(_flownet_row(path))
    rows.sort(key=lambda r: (r.holdout, r.basis, r.model))
    return rows


def _markdown(rows: list[Row]) -> str:
    lines = [
        "| " + " | ".join(HEADER) + " |",
        "|" + "|".join("---" for _ in HEADER) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row.as_list()) + " |")
    lines.append("")
    lines.append(
        "Each row holds out one attacker source for test; the other attackers train. "
        "Rows with the LOAO scoring basis score both models on the same windows, "
        "with a window labelled attack if any of its flows is an attack. The threshold "
        "is set on validation benign windows only. ROC/PR are threshold-free. The four "
        "folds share benign traffic and are not independent samples."
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the LOAO summary as Markdown and CSV."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=Path("data/runs"))
    parser.add_argument("--out", type=Path, default=Path("data/runs/loao_summary"))
    args = parser.parse_args(argv)

    rows = collect(args.runs)
    if not rows:
        print(f"no loao_*.json run logs under {args.runs}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    md_path = args.out.with_suffix(".md")
    csv_path = args.out.with_suffix(".csv")
    md_path.write_text(_markdown(rows), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for row in rows:
            writer.writerow(row.as_list())
    print(_markdown(rows))
    print(f"wrote {md_path} and {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
