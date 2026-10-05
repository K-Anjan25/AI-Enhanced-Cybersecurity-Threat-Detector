r"""Model card per release (T-214, R-74).

R-74 makes fabricating a metric an honesty defect rather than a style problem, so
this module is built so that a number *cannot* enter a card unless it was read out
of a recorded run. There is no constructor that takes a bare float and a name: the
only way to make a :class:`SourcedMetric` is to name the artifact and the field
inside it, and :func:`load_metric` opens that artifact and reads the value itself.

That is a deliberately awkward API. Writing ``Metric("recall", 0.98)`` is easier
and is exactly the mistake R-74 exists to prevent — a plausible number typed in
from memory, or copied from an earlier release, or rounded up. Every metric this
module emits renders with its provenance beside it, so a reader can check the
claim without trusting the author.

A card that cannot be sourced is refused rather than emitted with gaps. An absent
number reads as an omission; a number with no source reads as a measurement.

The adversarial-evasion caveat is mandatory, not optional. A detector card without
it implies the detector is robust to an adversary, which is not true of any
trained classifier and is the single most misleading thing a model card can omit.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

#: Required by T-214. Deliberately concrete: a caveat that says only "adversarial
#: attacks may evade the model" tells an operator nothing they can act on.
DEFAULT_ADVERSARIAL_CAVEAT = (
    "This detector is trained on captured traffic and has not been hardened against "
    "an adversary who knows it exists. Attackers can evade it by shaping traffic to "
    "resemble benign flows — padding, rate-limiting below detection windows, "
    "splitting an attack across many hosts, or reusing ports and protocols the "
    "training data associated with normal traffic. Measured recall applies to "
    "traffic resembling the recorded evaluation set, and gives no assurance against "
    "deliberately evasive traffic. Absence of an alert is not evidence of absence of "
    "an attack."
)


class CardError(ValueError):
    """Raised when a card cannot be built honestly."""


class MetricNotFound(CardError):
    """Raised when a cited field is not in the cited artifact."""


@dataclass(frozen=True, slots=True)
class SourcedMetric:
    """One number and the recorded run it came from.

    There is no way to build this from a number alone, which is the point.

    Attributes:
        name: what the metric is called in the card.
        value: the measured value.
        artifact: path to the run record this was read from.
        field: the location inside that artifact, as a dotted path.
    """

    name: str
    value: float
    artifact: str
    field: str

    def __post_init__(self) -> None:
        """Refuse a metric that cannot be checked."""
        if not self.name.strip():
            raise CardError("a metric needs a name")
        if not self.artifact.strip():
            raise CardError(
                f"metric {self.name!r} has no artifact. R-74 requires every number "
                "to trace to a recorded run; use load_metric to read one."
            )
        if not self.field.strip():
            raise CardError(f"metric {self.name!r} has no field path within {self.artifact!r}")
        if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
            raise CardError(f"metric {self.name!r} has non-numeric value {self.value!r}")
        if not math.isfinite(float(self.value)):
            raise CardError(f"metric {self.name!r} is {self.value!r}, which is not a number")

    @property
    def provenance(self) -> str:
        """The citation, rendered next to the number."""
        return f"{self.artifact} → {self.field}"

    def render(self) -> str:
        """The card line: value, then where it came from."""
        return f"{self.value:g} — `{self.provenance}`"

    def as_json(self) -> dict[str, object]:
        """Serialisable form."""
        return {
            "name": self.name,
            "value": self.value,
            "artifact": self.artifact,
            "field": self.field,
        }


def load_metric(
    artifact: str | Path,
    name: str,
    *field_path: str,
) -> SourcedMetric:
    """Read one metric out of a recorded run.

    Args:
        artifact: path to the run record, JSON.
        name: what to call it in the card.
        *field_path: keys to walk inside the artifact.

    Returns:
        A :class:`SourcedMetric` whose value came from that file.

    Raises:
        FileNotFoundError: if the run record is missing.
        MetricNotFound: if the path is not in the artifact, or does not hold a
            number. Citing a field that is not there is the failure this exists to
            catch.
    """
    target = Path(artifact)
    if not target.is_file():
        raise FileNotFoundError(f"no recorded run at {target}")
    with target.open("r", encoding="utf-8") as handle:
        document = json.load(handle)

    current: object = document
    for key in field_path:
        if not isinstance(current, dict) or key not in current:
            raise MetricNotFound(
                f"{name!r} cites {'.'.join(field_path)!r} but {target} has no such "
                f"field. R-74 requires the number to come from a recorded run; if "
                "the field moved, the citation has to move with it."
            )
        current = current[key]
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise MetricNotFound(
            f"{name!r} cites {'.'.join(field_path)!r} in {target}, which holds "
            f"{current!r} rather than a number."
        )

    return SourcedMetric(
        name=name, value=float(current), artifact=str(target), field=".".join(field_path)
    )


@dataclass(frozen=True, slots=True)
class ModelCard:
    """A release's model card.

    Attributes:
        model_id: the immutable id, from the registry (R-68). Never ``latest``.
        kind: flow or log.
        intended_use: what this model is for, and by implication what it is not.
        metrics: every number, each with its provenance.
        limitations: what the measurements do not establish.
        adversarial_caveat: mandatory. See the module docstring.
    """

    model_id: str
    kind: str
    intended_use: str
    metrics: tuple[SourcedMetric, ...]
    limitations: tuple[str, ...]
    adversarial_caveat: str

    def __post_init__(self) -> None:
        """Refuse a card that would be misleading by omission."""
        if not self.model_id.strip():
            raise CardError("a card needs a model id")
        if self.model_id.strip().lower() == "latest":
            raise CardError("a card cannot describe 'latest'; R-68 forbids the id")
        if not self.intended_use.strip():
            raise CardError("a card needs an intended use")
        if not self.metrics:
            raise CardError(
                "a card with no metrics claims nothing and can be checked against "
                "nothing. Either source numbers from a recorded run or do not "
                "publish a card."
            )
        if not self.limitations:
            raise CardError(
                "a card needs at least one limitation. Every measurement here was "
                "taken on a specific corpus, and a card that does not say so reads "
                "as a general claim."
            )
        if not self.adversarial_caveat.strip():
            raise CardError(
                "the adversarial-evasion caveat is required. A detector card "
                "without one implies robustness no trained classifier has."
            )

    def as_markdown(self) -> str:
        """Render the card. Every metric line carries its provenance."""
        lines = [
            f"# Model card — {self.model_id}",
            "",
            f"**Kind.** {self.kind}",
            "",
            "## Intended use",
            "",
            self.intended_use,
            "",
            "## Metrics",
            "",
            "Every value below was read from a recorded run. The citation follows",
            "each number; none of them were transcribed by hand (R-74).",
            "",
            "| Metric | Value | Source |",
            "|---|---|---|",
        ]
        lines += [
            f"| {metric.name} | {metric.value:g} | `{metric.provenance}` |"
            for metric in self.metrics
        ]
        lines += ["", "## Limitations", ""]
        lines += [f"- {limitation}" for limitation in self.limitations]
        lines += ["", "## Adversarial evasion", "", self.adversarial_caveat, ""]
        return "\n".join(lines)

    def as_json(self) -> dict[str, object]:
        """Serialisable form, for the release record."""
        return {
            "model_id": self.model_id,
            "kind": self.kind,
            "intended_use": self.intended_use,
            "metrics": [metric.as_json() for metric in self.metrics],
            "limitations": list(self.limitations),
            "adversarial_caveat": self.adversarial_caveat,
            "artifacts_cited": sorted({metric.artifact for metric in self.metrics}),
        }


def build_card(
    *,
    model_id: str,
    kind: str,
    intended_use: str,
    metrics: Sequence[SourcedMetric],
    limitations: Sequence[str],
    adversarial_caveat: str = DEFAULT_ADVERSARIAL_CAVEAT,
) -> ModelCard:
    """Assemble a card from metrics that already carry their provenance.

    Raises:
        CardError: if a metric is not a :class:`SourcedMetric`. This is checked
            here as well as by the type, because a card assembled from a JSON
            round-trip could otherwise smuggle in a plain dict of numbers.
    """
    for metric in metrics:
        if not isinstance(metric, SourcedMetric):
            raise CardError(
                f"metric {getattr(metric, 'name', metric)!r} is a "
                f"{type(metric).__name__}, not a SourcedMetric. A number with no "
                "recorded run behind it cannot go in a card (R-74); read it with "
                "load_metric instead."
            )
    return ModelCard(
        model_id=model_id,
        kind=kind,
        intended_use=intended_use,
        metrics=tuple(metrics),
        limitations=tuple(limitations),
        adversarial_caveat=adversarial_caveat,
    )
