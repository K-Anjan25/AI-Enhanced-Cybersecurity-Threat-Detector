"""Load a trained LogNet bundle and score a window of log messages.

A bundle is written by :func:`aegis_ml.training.lognet_train.train_bundle`. This
module reads it back. Scoring needs the template vocabulary, the threshold and
the weights together, so they are loaded as one unit or not at all.

The score is a monotone map of the hypersphere distance around the threshold:
``score = 1 / (1 + exp(-4 * (distance / threshold - 1)))``. A window exactly at the
threshold scores 0.5, twice the threshold scores about 0.98, and a window near the
centre scores close to 0. The map is a presentation choice, not a probability;
the threshold is what carries the decision.

PyTorch is imported when a bundle is loaded, not when this module is imported, so
the service still starts without torch (see ``test_serving_without_torch``).
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aegis_ml.data.log_parsers import TemplateMiner
from aegis_ml.training.lognet_train import (
    BUNDLE_SCHEMA,
    META_FILE,
    UNKNOWN_ID,
    WEIGHTS_FILE,
    template_index,
)


class BundleError(RuntimeError):
    """The bundle is missing, malformed, or built by an incompatible version."""


@dataclass(frozen=True)
class LogNetScore:
    """One scored window."""

    score: float
    distance: float
    threshold: float
    model_id: str


def anomaly_score(distance: float, threshold: float) -> float:
    """Map a distance to ``[0, 1]`` with 0.5 at the threshold."""
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    return 1.0 / (1.0 + math.exp(-4.0 * (distance / threshold - 1.0)))


class LogNetBundle:
    """A loaded LogNet, ready to score windows. Construct with :meth:`load`."""

    def __init__(
        self,
        *,
        model: Any,
        miner: TemplateMiner,
        index: dict[str, int],
        threshold: float,
        window: int,
        model_id: str,
    ) -> None:
        """Hold the loaded parts. Use :meth:`load`, which validates them first."""
        self._model = model
        self._miner = miner
        self._index = index
        self.threshold = threshold
        self.window = window
        self.model_id = model_id

    @classmethod
    def load(cls, directory: str | Path) -> LogNetBundle:
        """Read and validate a bundle directory. Raises :class:`BundleError` on any problem."""
        import torch  # noqa: PLC0415 - optional extra, imported only when a bundle is loaded

        from aegis_ml.models.lognet import LogNet, LogNetConfig  # noqa: PLC0415

        root = Path(directory)
        meta_path = root / META_FILE
        weights_path = root / WEIGHTS_FILE
        if not meta_path.is_file() or not weights_path.is_file():
            raise BundleError(f"no LogNet bundle in {root}")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise BundleError(f"bundle metadata is not valid JSON: {error}") from error
        if meta.get("schema") != BUNDLE_SCHEMA:
            raise BundleError(f"unsupported bundle schema {meta.get('schema')!r}")

        miner = TemplateMiner.model_validate(meta["miner"])
        index = template_index(miner)
        config = LogNetConfig(**meta["model_config"])
        if config.vocab_size != len(index) + 2:
            raise BundleError("vocabulary size does not match the saved templates")

        model = LogNet(config)
        state = torch.load(weights_path, map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        model.eval()

        return cls(
            model=model,
            miner=miner,
            index=index,
            threshold=float(meta["threshold"]),
            window=int(meta["train_config"]["window"]),
            model_id=str(meta["model_id"]),
        )

    def _tokens(self, messages: Sequence[str]) -> list[int]:
        return [self._index.get(self._miner.assign(m).template, UNKNOWN_ID) for m in messages]

    def window_distances(self, messages: Sequence[str]) -> list[float]:
        """Distance of each training-sized window in ``messages``.

        A request shorter than one window is scored as a single window of its
        own length. That is an approximation: the model was trained on windows
        of ``self.window`` lines.
        """
        import torch  # noqa: PLC0415

        tokens = self._tokens(messages)
        if not tokens:
            return []
        if len(tokens) <= self.window:
            chunks = [tokens]
        else:
            chunks = [tokens[s : s + self.window] for s in range(0, len(tokens), self.window)]
            chunks = [chunk for chunk in chunks if len(chunk) == self.window] or [tokens]
        distances: list[float] = []
        with torch.no_grad():
            for chunk in chunks:
                batch = torch.tensor([chunk], dtype=torch.long)
                distances.append(float(self._model(batch).distance[0]))
        return distances

    def score(self, messages: Sequence[str]) -> LogNetScore | None:
        """Score a request. The worst window decides. ``None`` when there is nothing to score."""
        distances = self.window_distances(messages)
        if not distances:
            return None
        worst = max(distances)
        return LogNetScore(
            score=anomaly_score(worst, self.threshold),
            distance=worst,
            threshold=self.threshold,
            model_id=self.model_id,
        )
