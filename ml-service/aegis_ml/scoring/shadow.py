r"""Shadow-mode scoring (T-213, architecture.md §8).

A model is promoted to ``staging``, shadow-scores live traffic, and only then owns
alerts. The point is to find out what a new model would have done before it is
allowed to do it: a model that fires on 40% of benign traffic is discovered here
with no incident attached, rather than after it has buried a triage queue.

**The harness cannot publish an alert, because it holds no reference to the alert
path.** That is a deliberate structural choice rather than a guard clause. A
``if shadow_mode: return`` check has to be remembered at every call site and fails
open the moment someone adds a new one; a harness constructed without an alert sink
has nothing to call. The acceptance criterion is that shadow scores are recorded
*without producing alerts*, and the only way to be certain of that is for the code
to have no route to one. The test asserts both halves: scores are recorded, and a
spy on the alert path sees nothing.

**"Comparable" is a measurement, not an impression.** The comparison is PSI between
the shadow model's score distribution and the active model's, using T-211's
implementation and its 0.25 threshold. Bin edges come from the *active* model's
scores, so the shadow distribution is measured against the incumbent's own
partition rather than a neutral one — the question is whether the new model looks
like the old one, not whether it looks uniform.

Note what a low PSI does and does not establish. Two models that agree on
distribution can still disagree on *which* windows they flag, and this module
reports that too via :attr:`ShadowComparison.disagreement_rate`. A shadow model
that passes on distribution alone could be swapping one set of false positives for
a different set of equal size.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from aegis_ml.scoring.drift import PSI_DRIFT_THRESHOLD, band_for, numeric_psi

#: Default bins for the score-distribution comparison.
SCORE_BINS = 10


class Scorer(Protocol):
    """Anything that turns a window into a score and knows which model it is."""

    model_id: str

    def score(self, window: object) -> float:
        """Score one window."""
        ...


class ShadowRecorder(Protocol):
    """Where shadow scores go. Deliberately not an alert sink."""

    def record(self, entry: ShadowScore) -> None:
        """Store one shadow score."""
        ...


class InMemoryShadowRecorder:
    """Keeps every shadow score, for tests and for the offline comparison."""

    def __init__(self) -> None:
        """Start empty."""
        self.entries: list[ShadowScore] = []

    def record(self, entry: ShadowScore) -> None:
        """Append one shadow score."""
        self.entries.append(entry)

    def scores(self) -> list[float]:
        """Just the shadow scores, in recording order."""
        return [entry.score for entry in self.entries]


@dataclass(frozen=True, slots=True)
class ShadowScore:
    """One window scored by the shadow model, alongside the active model's score.

    Attributes:
        window_id: which window this was.
        score: the shadow model's score.
        shadow_model_id: the model that produced ``score``.
        active_model_id: the incumbent, or ``None`` when there is none.
        active_score: the incumbent's score for the same window, for pairing.
        alerted: always ``False``. Present so a reader of the record can see that
            the absence of an alert is the designed behaviour and not an omission.
    """

    window_id: str
    score: float
    shadow_model_id: str
    active_model_id: str | None
    active_score: float | None
    alerted: bool = False


@dataclass(frozen=True, slots=True)
class ShadowComparison:
    """How the shadow model's scores relate to the active model's.

    Attributes:
        psi: population stability index, active scores as the reference.
        band: interpretation of ``psi``.
        comparable: whether ``psi`` is within the threshold.
        threshold: the threshold ``comparable`` was decided against.
        pairs: windows both models scored.
        disagreement_rate: fraction of windows where the two models land on
            opposite sides of the alert threshold. Distribution agreement does not
            bound this, so it is reported separately.
        alert_threshold: the score at which an alert would fire.
        shadow_alerts: windows the shadow model would have alerted on.
        active_alerts: windows the active model did alert on.
    """

    psi: float
    band: str
    comparable: bool
    threshold: float
    pairs: int
    disagreement_rate: float
    alert_threshold: float
    shadow_alerts: int
    active_alerts: int

    def as_json(self) -> dict[str, object]:
        """Serialisable form, for the release record."""
        return {
            "psi": self.psi,
            "band": self.band,
            "comparable": self.comparable,
            "threshold": self.threshold,
            "pairs": self.pairs,
            "disagreement_rate": self.disagreement_rate,
            "alert_threshold": self.alert_threshold,
            "shadow_alerts": self.shadow_alerts,
            "active_alerts": self.active_alerts,
        }


class ShadowHarness:
    """Scores windows through a staging model and records what it saw.

    There is no ``alert_sink`` parameter and no ``publish`` method. Adding one
    would defeat the guarantee this module exists to provide, so a caller that
    wants shadow scores to raise alerts is asking for a normal scorer instead.
    """

    def __init__(
        self,
        shadow: Scorer,
        recorder: ShadowRecorder,
        *,
        active: Scorer | None = None,
        alert_threshold: float = 0.5,
    ) -> None:
        """Wire a shadow scorer to a recorder.

        Args:
            shadow: the staging model.
            recorder: where scores are stored.
            active: the incumbent, for pairing. Optional, because a first model
                has nothing to be compared against.
            alert_threshold: the score at which an alert would fire, used only for
                the disagreement count. The harness never acts on it.
        """
        self._shadow = shadow
        self._recorder = recorder
        self._active = active
        self._alert_threshold = alert_threshold

    @property
    def shadow_model_id(self) -> str:
        """The staging model's id."""
        return self._shadow.model_id

    def score(self, window_id: str, window: object) -> ShadowScore:
        """Score one window through the shadow model and record it.

        The active model is scored too when one is configured, so the two score
        the same window and the comparison is paired rather than two unrelated
        samples.

        No alert is produced, and nothing here can produce one.
        """
        shadow_score = float(self._shadow.score(window))
        active_score = float(self._active.score(window)) if self._active else None
        entry = ShadowScore(
            window_id=window_id,
            score=shadow_score,
            shadow_model_id=self._shadow.model_id,
            active_model_id=self._active.model_id if self._active else None,
            active_score=active_score,
        )
        self._recorder.record(entry)
        return entry

    def score_all(self, windows: Sequence[tuple[str, object]]) -> list[ShadowScore]:
        """Score a batch of ``(window_id, window)`` pairs."""
        return [self.score(window_id, window) for window_id, window in windows]

    def compare(
        self,
        entries: Sequence[ShadowScore] | None = None,
        *,
        bins: int = SCORE_BINS,
        threshold: float = PSI_DRIFT_THRESHOLD,
    ) -> ShadowComparison:
        """Compare the shadow score distribution against the active model's.

        Args:
            entries: scores to compare. Defaults to everything the recorder holds,
                when the recorder is the in-memory one.
            bins: bins for the PSI computation.
            threshold: PSI above which the distributions are not comparable.

        Raises:
            ValueError: if there is no active model to compare against, or fewer
                than two paired scores. A comparison of one distribution against
                nothing is not a comparison, and silently calling it comparable
                would be worse than refusing.
        """
        if self._active is None:
            raise ValueError(
                "no active model is configured, so there is nothing to compare "
                "against. A shadow model with no incumbent cannot be judged "
                "comparable; promote it on its own merits or configure an active "
                "model first."
            )
        if entries is None:
            if not isinstance(self._recorder, InMemoryShadowRecorder):
                raise ValueError(
                    "no entries were supplied and the recorder does not expose "
                    "them; pass the scores to compare explicitly"
                )
            entries = self._recorder.entries

        # Pull both scores out while the None check is in scope. Filtering
        # first and reading the field afterwards leaves the type checker
        # unable to narrow a frozen dataclass attribute across a
        # comprehension, and a cast would assert what the code never checked.
        paired: list[tuple[float, float]] = []
        for entry in entries:
            if entry.active_score is not None:
                paired.append((float(entry.score), float(entry.active_score)))
        if len(paired) < 2:
            raise ValueError(
                f"need at least 2 paired scores to compare a distribution, got " f"{len(paired)}"
            )

        shadow_scores = [shadow for shadow, _ in paired]
        active_scores = [active for _, active in paired]
        psi = numeric_psi(active_scores, shadow_scores, bins=bins)

        shadow_alerts = sum(1 for value in shadow_scores if value >= self._alert_threshold)
        active_alerts = sum(1 for value in active_scores if value >= self._alert_threshold)
        disagreements = sum(
            1
            for shadow, active in zip(shadow_scores, active_scores, strict=True)
            if (shadow >= self._alert_threshold) != (active >= self._alert_threshold)
        )

        return ShadowComparison(
            psi=psi,
            band=band_for(psi),
            comparable=psi <= threshold,
            threshold=threshold,
            pairs=len(paired),
            disagreement_rate=disagreements / len(paired),
            alert_threshold=self._alert_threshold,
            shadow_alerts=shadow_alerts,
            active_alerts=active_alerts,
        )
