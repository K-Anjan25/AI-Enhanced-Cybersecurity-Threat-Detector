"""Preprocessing: standardisation, vocabularies and PII redaction (T-105).

The rule that matters here is R-62: **a scaler or vocabulary fitted on anything
other than the training split is leakage.** Every fit method therefore takes the
training rows and nothing else, and the fitted artifact is serialised whole so a
later stage cannot quietly refit it. ``audit.py`` checks that the statistics in
a fitted scaler really came from the training rows.

PII redaction is pseudonymisation, not deletion. An IP address is personal data
under GDPR, but it is also the entity key that R-61's entity-disjoint split is
built on — dropping it would make the split impossible. So addresses are replaced
by a keyed digest: the address itself is not recoverable without the key, while
flows from the same host still map to the same value and entity boundaries
survive.

Two honest limits:

* Only IPv4 addresses and MAC-like strings are redacted. Free-text fields that
  embed a hostname inside a message are not scanned.
* Pseudonymisation is reversible by anyone holding the key, so the key is a
  secret (R-50) and must never be committed or logged.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import os
from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

#: Index reserved for a value never seen during fitting.
UNKNOWN_INDEX: Final[int] = 0

#: A digest this long cannot be brute-forced back to an address in the /24s the
#: benchmark datasets use, while staying short enough to log.
PSEUDONYM_BYTES: Final[int] = 8


def redact(value: str, *, key: bytes) -> str:
    """Replace an identifier with a keyed, stable pseudonym.

    Args:
        value: The raw identifier, e.g. an IPv4 address in dotted form.
        key: A secret key. The same key maps the same value to the same
            pseudonym; a different key produces unrelated output.

    Raises:
        ValueError: if the key is shorter than 32 bytes, matching the minimum
            the API's own secret requires.
    """
    if len(key) < 32:
        msg = "redaction key must be at least 32 bytes"
        raise ValueError(msg)
    digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()
    return digest[:PSEUDONYM_BYTES].hex()


class StandardScaler(BaseModel):
    """Mean/std standardisation, fitted on the training split only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    stds: tuple[float, ...]

    @classmethod
    def fit(cls, rows: Sequence[Sequence[float]], names: Sequence[str]) -> StandardScaler:
        """Compute per-feature mean and population standard deviation."""
        if not rows:
            msg = "cannot fit a scaler on zero rows"
            raise ValueError(msg)
        width = len(names)
        for index, row in enumerate(rows):
            if len(row) != width:
                msg = f"row {index} has {len(row)} values, expected {width}"
                raise ValueError(msg)
        means = tuple(sum(r[i] for r in rows) / len(rows) for i in range(width))
        stds = tuple(
            math.sqrt(sum((r[i] - means[i]) ** 2 for r in rows) / len(rows)) for i in range(width)
        )
        return cls(feature_names=tuple(names), means=means, stds=stds)

    def transform(self, values: Sequence[float]) -> list[float]:
        """Standardise one row.

        A feature with zero variance in training is left centred rather than
        divided by zero: every value that reaches it is equal to the mean, so
        the informative value is 0.0 and an inf would poison the model.
        """
        if len(values) != len(self.feature_names):
            msg = f"expected {len(self.feature_names)} values, got {len(values)}"
            raise ValueError(msg)
        return [
            0.0 if std == 0.0 else (value - mean) / std
            for value, mean, std in zip(values, self.means, self.stds, strict=True)
        ]


class Vocabulary(BaseModel):
    """A closed set of categorical values seen in the training split."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: tuple[str, ...] = Field(description="Index 0 is reserved for unknown values.")

    @classmethod
    def fit(cls, observed: Iterable[str]) -> Vocabulary:
        """Build a vocabulary sorted for stability across runs."""
        return cls(values=("",) + tuple(sorted(set(observed))))

    def encode(self, value: str) -> int:
        """Index of ``value``, or UNKNOWN_INDEX if it was never seen in training.

        An unseen value is not an error: a production model must score traffic
        containing a protocol it has never seen. It is mapped to the reserved
        unknown slot instead of shifting every other index.
        """
        try:
            index = self.values.index(value)
        except ValueError:
            return UNKNOWN_INDEX
        return index


class Preprocessor(BaseModel):
    """A fitted preprocessing bundle, serialisable as a single artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scaler: StandardScaler
    vocabularies: Mapping[str, Vocabulary]

    def save(self, path: str) -> None:
        """Write the bundle as JSON. Deterministic for a given input."""
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: str) -> Preprocessor:
        """Read a bundle back. A round trip must be lossless."""
        with open(path, encoding="utf-8") as handle:
            return cls.model_validate_json(handle.read())
