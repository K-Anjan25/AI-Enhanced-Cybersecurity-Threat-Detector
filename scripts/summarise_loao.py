"""Summarise leave-one-attacker-out run logs into one table.

Reads ``loao_baselines_<entity>.json`` (from run_baselines.py) and
``loao_flownet_<entity>.json`` (from train_flownet.py) and writes a Markdown table
and a CSV, one row per (held-out attacker, model).

Threshold-free metrics (ROC-AUC, PR-AUC) come from the run logs unchanged. The
fixed-threshold columns use threshold 0.5, the same for every model. The best-F1
threshold is chosen on the test fold, so it is shown only for transparency and is
not used here.

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


@dataclass(frozen=True)
class Row:
    """One held-out attacker scored by one model."""

    holdout: str
    model: str
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

    def as_list(self) -> list[object]:
        """The row as table cells, in HEADER order."""
        return [
            self.holdout,
            self.model,
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
        ]


HEADER = [
    "held_out_attacker",
    "model",
    "test_positives",
    "test_negatives",
    "roc_auc",
    "pr_auc",
    "precision@0.5",
    "recall@0.5",
    "fpr@0.5",
    "tp",
    "fp",
    "fn",
    "tn",
]


def _rates(confusion: dict[str, int]) -> tuple[float, float, float]:
    tp, fp, fn, tn = (confusion[k] for k in ("tp", "fp", "fn", "tn"))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return precision, recall, fpr


def _baseline_rows(path: Path) -> list[Row]:
    data = json.loads(path.read_text(encoding="utf-8"))
    holdout = data["holdout_entity"]
    rows: list[Row] = []
    for model, body in data["models"].items():
        confusion = body["confusion"]
        precision, recall, fpr = _rates(confusion)
        rows.append(
            Row(
                holdout=holdout,
                model=model,
                positives=body["positives"],
                negatives=body["negatives"],
                roc_auc=body["metrics"]["roc_auc"],
                pr_auc=body["metrics"]["pr_auc"],
                precision=precision,
                recall=recall,
                fpr=fpr,
                tp=confusion["tp"],
                fp=confusion["fp"],
                fn=confusion["fn"],
                tn=confusion["tn"],
            )
        )
    return rows


def _flownet_row(path: Path) -> Row:
    data = json.loads(path.read_text(encoding="utf-8"))
    report = data["report"]
    confusion = report["confusion"]
    precision, recall, fpr = _rates(confusion)
    return Row(
        holdout=data["holdout_entity"],
        model="flownet",
        positives=report["positives"],
        negatives=report["negatives"],
        roc_auc=report["metrics"]["roc_auc"],
        pr_auc=report["metrics"]["pr_auc"],
        precision=precision,
        recall=recall,
        fpr=fpr,
        tp=confusion["tp"],
        fp=confusion["fp"],
        fn=confusion["fn"],
        tn=confusion["tn"],
    )


def collect(runs: Path) -> list[Row]:
    """Gather every LOAO run log in ``runs``, sorted by attacker then model."""
    rows: list[Row] = []
    for path in sorted(runs.glob("loao_baselines_*.json")):
        rows.extend(_baseline_rows(path))
    for path in sorted(runs.glob("loao_flownet_*.json")):
        rows.append(_flownet_row(path))
    rows.sort(key=lambda r: (r.holdout, r.model))
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
        "Fixed-threshold columns use 0.5. ROC/PR are threshold-free. The four folds "
        "share benign traffic and are not independent samples."
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
