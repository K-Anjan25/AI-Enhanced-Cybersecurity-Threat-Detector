"""LogNet training: from labelled log lines to a servable bundle.

The pipeline, in the order it runs:

1. **Time split, before anything is fitted.** Lines are cut at ``train_fraction``
   in arrival order. Only lines before the cut are used to mine the template
   vocabulary, so the held-out part never shapes the vocabulary it is scored with.
2. **Windows** of ``window`` consecutive lines, stepping by ``stride``. A window
   is labelled anomalous when any of its lines is. Windows that straddle the cut
   are dropped, so no window contributes to both training and evaluation.
3. **Training** on clean (unlabelled-as-anomalous) training windows only, with the
   masked-template objective plus the hypersphere objective. ``lognet.py`` documents
   why the hypersphere term must see benign traffic only.
4. **Threshold** = a quantile of the distances of the clean training windows. It is
   set from data the model was trained on, which is a known weakness; a separate
   calibration split is the stronger choice once there is enough data.
5. **Evaluation** on the held-out windows, reported with their counts. Small
   counts are reported as they are, not rounded into confidence.

The bundle written to ``out_dir`` is everything serving needs and nothing else:
``lognet.pt`` (weights), ``lognet.json`` (config, vocabulary, threshold, metrics,
data digest). See :mod:`aegis_ml.serving.lognet_bundle` for the loader.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch

from aegis_ml.data.log_parsers import TemplateMiner
from aegis_ml.models.lognet import LogNet, LogNetConfig, hypersphere_loss, masked_template_loss

#: Token ids reserved ahead of the template vocabulary. Id 0 is the mask (the
#: LogNetConfig default), id 1 is "a template this vocabulary has never seen".
MASK_ID = 0
UNKNOWN_ID = 1
FIRST_TEMPLATE_ID = 2

BUNDLE_SCHEMA = "lognet-bundle@1"
WEIGHTS_FILE = "lognet.pt"
META_FILE = "lognet.json"


@dataclass(frozen=True)
class LogNetTrainConfig:
    """Everything that changes a trained LogNet. Recorded in the bundle."""

    window: int = 50
    stride: int = 25
    train_fraction: float = 0.7
    epochs: int = 40
    batch_size: int = 16
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    threshold_quantile: float = 0.95
    seed: int = 1
    d_model: int = 64
    nhead: int = 4
    dim_feedforward: int = 128
    dropout: float = 0.1
    mask_ratio: float = 0.15

    def __post_init__(self) -> None:
        """Reject settings that would fail opaquely inside the loop."""
        if self.window < 4:
            raise ValueError("window must be at least 4 lines")
        if not 1 <= self.stride <= self.window:
            raise ValueError("stride must be between 1 and the window length")
        if not 0.2 <= self.train_fraction <= 0.9:
            raise ValueError("train_fraction must be between 0.2 and 0.9")
        if not 0.5 <= self.threshold_quantile < 1.0:
            raise ValueError("threshold_quantile must be in [0.5, 1)")


@dataclass(frozen=True)
class LogLine:
    """One labelled log line, in arrival order."""

    epoch: float
    message: str
    anomalous: bool
    #: Whether the line is at a non-info severity. Used only by the severity baseline
    #: rule that the promotion gate compares against; the model never sees it.
    flagged: bool = False


@dataclass
class TrainResult:
    """What a training run produced, for the caller and the bundle."""

    metrics: dict[str, Any] = field(default_factory=dict)
    history: list[float] = field(default_factory=list)


# ── pure helpers (tested without training) ──────────────────────────────────


def encode_lines(miner: TemplateMiner, messages: Sequence[str]) -> list[int]:
    """Map each message to a token id via its mined template.

    Templates that the vocabulary does not contain map to :data:`UNKNOWN_ID`
    rather than being forced into a near match.
    """
    index = template_index(miner)
    return [index.get(miner.assign(message).template, UNKNOWN_ID) for message in messages]


def template_index(miner: TemplateMiner) -> dict[str, int]:
    """Template text -> token id, in the miner's stored order."""
    return {
        " ".join(template): position + FIRST_TEMPLATE_ID
        for position, template in enumerate(miner.templates)
    }


def make_windows(
    tokens: Sequence[int], labels: Sequence[bool], window: int, stride: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cut a token stream into windows.

    Returns ``(x, y, starts)``: ``x`` is ``(n, window)`` int64 token ids, ``y`` is
    ``(n,)`` with 1 for anomalous, and ``starts`` the first line index of each window.
    """
    if len(tokens) != len(labels):
        raise ValueError("tokens and labels must be the same length")
    starts = list(range(0, len(tokens) - window + 1, stride))
    if not starts:
        raise ValueError(f"need at least {window} lines for one window, got {len(tokens)}")
    x = np.array([tokens[s : s + window] for s in starts], dtype=np.int64)
    y = np.array([int(any(labels[s : s + window])) for s in starts], dtype=np.int64)
    return x, y, np.array(starts, dtype=np.int64)


def mask_batch(
    x: torch.Tensor, mask_ratio: float, generator: torch.Generator
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Hide a share of positions for the masked-template objective.

    Returns ``(inputs, targets, mask)``. At least one position is always masked, so
    the loss is defined for every batch.
    """
    mask = torch.rand(x.shape, generator=generator) < mask_ratio
    if not bool(mask.any()):
        mask[0, 0] = True
    inputs = x.clone()
    inputs[mask] = MASK_ID
    return inputs, x, mask


def roc_auc(scores: np.ndarray, labels: np.ndarray) -> float | None:
    """ROC-AUC by the rank (Mann-Whitney) formulation. ``None`` if one class is absent."""
    positives = scores[labels == 1]
    negatives = scores[labels == 0]
    if positives.size == 0 or negatives.size == 0:
        return None
    # Average ranks for ties, so equal scores count as half a win, not as an order.
    combined = np.concatenate([positives, negatives])
    values, inverse, counts = np.unique(combined, return_inverse=True, return_counts=True)
    cumulative = np.cumsum(counts)
    average_rank = cumulative - (counts - 1) / 2.0
    ranks = average_rank[inverse.reshape(-1)]
    rank_sum = float(ranks[: positives.size].sum())
    n_pos, n_neg = positives.size, negatives.size
    return float((rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def threshold_from(distances: np.ndarray, quantile: float) -> float:
    """The distance above which a window is flagged, from clean training windows."""
    if distances.size == 0:
        raise ValueError("no clean training windows to set a threshold from")
    return float(np.quantile(distances, quantile))


def classify_metrics(
    distances: np.ndarray, labels: np.ndarray, threshold: float
) -> dict[str, Any]:
    """Confusion counts and rates at ``threshold``, plus ROC-AUC, for held-out windows."""
    predicted = (distances >= threshold).astype(np.int64)
    tp = int(((predicted == 1) & (labels == 1)).sum())
    fp = int(((predicted == 1) & (labels == 0)).sum())
    fn = int(((predicted == 0) & (labels == 1)).sum())
    tn = int(((predicted == 0) & (labels == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    return {
        "windows": int(labels.size),
        "anomalous_windows": int(labels.sum()),
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "roc_auc": roc_auc(distances, labels),
    }


def digest_lines(lines: Sequence[LogLine]) -> str:
    """Content hash of the training input, so a bundle names the exact data it saw."""
    hasher = hashlib.sha256()
    for line in lines:
        hasher.update(f"{line.epoch!r}\t{int(line.anomalous)}\t{line.message}\n".encode())
    return hasher.hexdigest()


# ── training ─────────────────────────────────────────────────────────────────


def build_model_config(vocab_size: int, cfg: LogNetTrainConfig) -> LogNetConfig:
    """The LogNet configuration for a vocabulary of ``vocab_size`` tokens."""
    return LogNetConfig(
        vocab_size=vocab_size,
        mask_token_id=MASK_ID,
        d_model=cfg.d_model,
        nhead=cfg.nhead,
        dim_feedforward=cfg.dim_feedforward,
        dropout=cfg.dropout,
        mask_ratio=cfg.mask_ratio,
    )


def train_model(
    model: LogNet, x_clean: np.ndarray, cfg: LogNetTrainConfig, result: TrainResult
) -> LogNet:
    """Fit ``model`` on clean windows. Appends the per-epoch loss to ``result.history``."""
    torch.manual_seed(cfg.seed)
    generator = torch.Generator().manual_seed(cfg.seed)
    rng = random.Random(cfg.seed)  # noqa: S311 - shuffling order, not security
    optimiser = torch.optim.AdamW(
        model.parameters(), lr=cfg.learning_rate, weight_decay=cfg.weight_decay
    )
    data = torch.tensor(x_clean, dtype=torch.long)
    order = list(range(data.shape[0]))
    model.train()
    for _epoch in range(cfg.epochs):
        rng.shuffle(order)
        total = 0.0
        batches = 0
        for start in range(0, len(order), cfg.batch_size):
            batch = data[order[start : start + cfg.batch_size]]
            inputs, targets, mask = mask_batch(batch, cfg.mask_ratio, generator)
            output = model(inputs)
            loss = masked_template_loss(output, targets, mask) + hypersphere_loss(output)
            optimiser.zero_grad()
            loss.backward()  # type: ignore[no-untyped-call]
            optimiser.step()
            total += float(loss.detach())
            batches += 1
        result.history.append(total / max(batches, 1))
    model.eval()
    return model


def score_distances(model: LogNet, x: np.ndarray, batch_size: int = 256) -> np.ndarray:
    """Hypersphere distance for each window, with gradients off."""
    out: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, x.shape[0], batch_size):
            batch = torch.tensor(x[start : start + batch_size], dtype=torch.long)
            out.append(model(batch).distance.numpy())
    return np.concatenate(out) if out else np.zeros(0)


def _severity_baseline_auc(
    lines: Sequence[LogLine], starts: np.ndarray, eval_mask: np.ndarray, window: int
) -> float | None:
    """ROC-AUC of "share of flagged lines in the window" on the held-out windows.

    This is the trivial rule the model has to beat. It is recorded with every run so
    that a candidate is never judged in isolation.
    """
    flags = np.array([line.flagged for line in lines], dtype=float)
    eval_starts = starts[eval_mask]
    scores = np.array([flags[s : s + window].mean() for s in eval_starts])
    labels = np.array(
        [any(line.anomalous for line in lines[s : s + window]) for s in eval_starts], dtype=int
    )
    return roc_auc(scores, labels)


def train_bundle(lines: Sequence[LogLine], out_dir: Path, cfg: LogNetTrainConfig) -> dict[str, Any]:
    """Run the whole pipeline and write the bundle. Returns the metrics written to it."""
    if len(lines) < cfg.window * 4:
        raise ValueError(f"too few lines ({len(lines)}) for window {cfg.window}")
    cut = int(len(lines) * cfg.train_fraction)
    train_lines = lines[:cut]

    # 1. Vocabulary from the training part only.
    miner = TemplateMiner.fit(line.message for line in train_lines)
    tokens = encode_lines(miner, [line.message for line in lines])
    labels = [line.anomalous for line in lines]

    # 2. Windows, and the split that keeps straddling windows out of both sides.
    x, y, starts = make_windows(tokens, labels, cfg.window, cfg.stride)
    train_mask = starts + cfg.window <= cut
    eval_mask = starts >= cut
    x_train, y_train = x[train_mask], y[train_mask]
    x_eval, y_eval = x[eval_mask], y[eval_mask]
    x_clean = x_train[y_train == 0]
    if x_clean.shape[0] < 8:
        raise ValueError(f"only {x_clean.shape[0]} clean training windows; need at least 8")

    # 3. Train on clean windows only.
    vocab_size = len(miner.templates) + FIRST_TEMPLATE_ID
    model_config = build_model_config(vocab_size, cfg)
    model = LogNet(model_config)
    result = TrainResult()
    train_model(model, x_clean, cfg, result)

    # 4. Threshold from clean training windows; 5. evaluation on held-out windows.
    threshold = threshold_from(score_distances(model, x_clean), cfg.threshold_quantile)
    metrics = classify_metrics(score_distances(model, x_eval), y_eval, threshold)
    metrics["train_windows"] = int(x_train.shape[0])
    metrics["train_clean_windows"] = int(x_clean.shape[0])
    metrics["straddling_windows_dropped"] = int(
        x.shape[0] - x_train.shape[0] - x_eval.shape[0]
    )
    metrics["final_train_loss"] = result.history[-1] if result.history else None
    metrics["baseline_severity_auc"] = _severity_baseline_auc(lines, starts, eval_mask, cfg.window)

    # 6. Bundle.
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out_dir / WEIGHTS_FILE)
    meta = {
        "schema": BUNDLE_SCHEMA,
        "model_id": f"lognet-v1-{digest_lines(lines)[:12]}",
        "model_config": asdict(model_config),
        "train_config": asdict(cfg),
        "miner": miner.model_dump(mode="json"),
        "threshold": threshold,
        "data_sha256": digest_lines(lines),
        "lines": len(lines),
        "metrics": metrics,
        "loss_history": result.history,
    }
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    return metrics
