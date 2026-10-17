"""Serve a trained FlowNet checkpoint over ``flow@1`` windows.

The training run (``scripts/train_flownet.py --checkpoint``) writes four files into
one directory: the weights, the architecture config, the fitted preprocessor (scaler
and vocabularies, R-62) and the ``eval@2`` report measured on this model. This module
loads them and scores a window through the same encoding training used
(:func:`aegis_ml.training.baselines.encode_row`), so a served score is the score the
evaluation was measured on, not an approximation of it.

A window is padded with zeros to the training length after standardisation, exactly
as training does: a zero in standardised space is the training mean.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aegis_ml.data.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, extract_flow_window
from aegis_ml.data.preprocess import Preprocessor
from aegis_ml.data.records import FlowRecord
from aegis_ml.data.windowing import WindowKey
from aegis_ml.scoring.explanation import Reason, explain
from aegis_ml.training.baselines import encode_row

if TYPE_CHECKING:
    from aegis_ml.models.flownet import FlowNet

WEIGHTS_FILE = "flownet.pt"
CONFIG_FILE = "flownet.config.json"
PREPROCESSOR_FILE = "flownet.preprocessor.json"
EVAL_FILE = "flownet.eval.json"


class CheckpointError(RuntimeError):
    """The checkpoint directory is missing a file or does not match its config."""


@dataclass(frozen=True, slots=True)
class FlowNetScore:
    """One scored window.

    Attributes:
        score: the anomaly probability, in ``[0, 1]``.
        model_id: the model that produced it, from the checkpoint config.
        reasons: the top features by occlusion attribution (FR-14).
        explanation_unavailable: set when attribution failed. The score still stands.
        flows: how many flows the window held.
    """

    score: float
    model_id: str
    reasons: tuple[Reason, ...]
    explanation_unavailable: bool
    flows: int


def sha256_file(path: str) -> str:
    """Content address of an artifact file (R-68)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def feature_names(preprocessor: Preprocessor) -> tuple[str, ...]:
    """Column names in the order :func:`encode_row` writes them."""
    names: list[str] = list(NUMERIC_FEATURES)
    for name in CATEGORICAL_FEATURES:
        names.extend(f"{name}={value}" for value in preprocessor.vocabularies[name].values)
    return tuple(names)


class FlowNetScorer:
    """A loaded FlowNet checkpoint that scores ``flow@1`` windows."""

    def __init__(
        self,
        model: FlowNet,
        preprocessor: Preprocessor,
        *,
        model_id: str,
        window_size: int,
        window_key: WindowKey,
        sha256: str,
    ) -> None:
        """Wrap already-loaded parts; use :meth:`load` to read them from disk."""
        self._model = model
        self._preprocessor = preprocessor
        self.model_id = model_id
        self.window_size = window_size
        self.window_key = window_key
        self.sha256 = sha256
        self._names = feature_names(preprocessor)
        if len(self._names) != model.config.input_dim:
            raise CheckpointError(
                f"preprocessor encodes {len(self._names)} columns but the model expects "
                f"{model.config.input_dim}"
            )
        self._model.eval()

    @classmethod
    def load(cls, directory: str) -> FlowNetScorer:
        """Read a checkpoint directory written by the training script.

        Raises:
            CheckpointError: if a file is missing or the parts disagree.
        """
        # torch is the [training] extra, not a core dependency. Importing it here, not at
        # module level, lets the service start and report "no model" without it.
        try:
            import torch  # noqa: PLC0415

            from aegis_ml.models.flownet import FlowNet, FlowNetConfig  # noqa: PLC0415
        except ImportError as exc:
            raise CheckpointError(
                "the flow model needs torch: install ml-service[training]"
            ) from exc

        paths = {name: os.path.join(directory, name) for name in (WEIGHTS_FILE, CONFIG_FILE)}
        preprocessor_path = os.path.join(directory, PREPROCESSOR_FILE)
        for path in (*paths.values(), preprocessor_path):
            if not os.path.isfile(path):
                raise CheckpointError(f"checkpoint is missing {path}")
        with open(paths[CONFIG_FILE], encoding="utf-8") as handle:
            config = json.load(handle)
        model = FlowNet(
            FlowNetConfig(
                input_dim=int(config["input_dim"]),
                d_model=int(config["d_model"]),
                nhead=int(config["nhead"]),
                dim_feedforward=int(config["dim_feedforward"]),
                max_seq_len=int(config["max_seq_len"]),
            )
        )
        state = torch.load(paths[WEIGHTS_FILE], map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        return cls(
            model,
            Preprocessor.load(preprocessor_path),
            model_id=str(config["model_id"]),
            window_size=int(config["window_size"]),
            window_key=WindowKey(config["window_key"]),
            sha256=sha256_file(paths[WEIGHTS_FILE]),
        )

    def encode(self, flows: Sequence[FlowRecord]) -> list[list[float]]:
        """Encode one window (at most ``window_size`` flows) and pad it to length."""
        features = extract_flow_window(flows, key=self.window_key)
        rows = [encode_row(row, self._preprocessor) for row in features]
        padding = [0.0] * len(self._names)
        return rows + [padding] * (self.window_size - len(rows))

    def score(self, flows: Sequence[FlowRecord]) -> FlowNetScore:
        """Score one window.

        Longer windows are cut into ``window_size`` chunks and the highest chunk score is
        reported, so a long burst is not diluted by quiet traffic.

        Raises:
            ValueError: if the window is empty.
        """
        if not flows:
            raise ValueError("cannot score an empty window")
        chunks = [
            flows[start : start + self.window_size]
            for start in range(0, len(flows), self.window_size)
        ]
        best: tuple[float, list[list[float]]] | None = None
        for chunk in chunks:
            matrix = self.encode(chunk)
            value = _probability(self._model, matrix)
            if best is None or value > best[0]:
                best = (value, matrix)
        if best is None:  # unreachable: chunks is non-empty because flows is
            raise ValueError("cannot score an empty window")
        value, matrix = best
        baseline = [0.0] * len(self._names)
        explanation = explain(self._model, matrix, baseline, self._names, score=value)
        return FlowNetScore(
            score=value,
            model_id=self.model_id,
            reasons=explanation.reasons,
            explanation_unavailable=explanation.unavailable,
            flows=len(flows),
        )


def _probability(model: FlowNet, matrix: list[list[float]]) -> float:
    import torch  # noqa: PLC0415

    with torch.no_grad():
        logits = model(torch.tensor([matrix], dtype=torch.float32)).anomaly_logits
    return float(torch.sigmoid(logits)[0])
