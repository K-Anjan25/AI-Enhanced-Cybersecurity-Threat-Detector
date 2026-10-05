r"""Tests for the shadow-mode scoring harness (T-213).

The acceptance criterion has two halves and they are tested separately: shadow
scores are recorded, and no alerts are produced. The second half is the one that
matters, and it is tested structurally — a harness that merely checks a flag can
grow a call site that forgets the check, while a harness with no reference to the
alert path cannot.
"""

from __future__ import annotations

import inspect

import pytest
from aegis_ml.scoring.shadow import (
    InMemoryShadowRecorder,
    ShadowHarness,
    ShadowScore,
)


class _FixedScorer:
    """Returns a scripted score per window, so distributions can be arranged."""

    def __init__(self, model_id: str, scores: dict[str, float]) -> None:
        self.model_id = model_id
        self._scores = scores
        self.scored: list[str] = []

    def score(self, window: object) -> float:
        key = str(window)
        self.scored.append(key)
        return self._scores[key]


class _SpyAlertSink:
    """Stands in for the real alert path, to prove it is never reached."""

    def __init__(self) -> None:
        self.published: list[object] = []

    def publish(self, window: object) -> None:
        self.published.append(window)


def _harness(
    shadow_scores: dict[str, float],
    active_scores: dict[str, float] | None = None,
    *,
    alert_threshold: float = 0.5,
) -> tuple[ShadowHarness, InMemoryShadowRecorder]:
    recorder = InMemoryShadowRecorder()
    active = _FixedScorer("flownet@1.0.0", active_scores or {}) if active_scores else None
    harness = ShadowHarness(
        _FixedScorer("flownet@2.0.0", shadow_scores),
        recorder,
        active=active,
        alert_threshold=alert_threshold,
    )
    return harness, recorder


def _scored(
    shadow_scores: dict[str, float],
    active_scores: dict[str, float] | None = None,
    *,
    alert_threshold: float = 0.5,
) -> ShadowHarness:
    """A harness that has already scored every window in ``shadow_scores``.

    The comparison reads what the recorder holds, so a harness that has not been
    run has nothing to compare and would fail for the wrong reason.
    """
    harness, _ = _harness(shadow_scores, active_scores, alert_threshold=alert_threshold)
    harness.score_all([(key, key) for key in shadow_scores])
    return harness


class TestScoresAreRecorded:
    """The first half of the criterion."""

    def test_one_score_is_recorded(self) -> None:
        harness, recorder = _harness({"w1": 0.9})

        entry = harness.score("w1", "w1")

        assert entry.score == 0.9
        assert entry.window_id == "w1"
        assert entry.shadow_model_id == "flownet@2.0.0"
        assert recorder.entries == [entry]

    def test_a_batch_is_recorded_in_order(self) -> None:
        harness, recorder = _harness({"w1": 0.1, "w2": 0.2, "w3": 0.3})

        entries = harness.score_all([("w1", "w1"), ("w2", "w2"), ("w3", "w3")])

        assert [entry.window_id for entry in entries] == ["w1", "w2", "w3"]
        assert recorder.scores() == [0.1, 0.2, 0.3]

    def test_the_active_score_is_paired_to_the_same_window(self) -> None:
        """Pairing is what makes the comparison meaningful."""
        harness, recorder = _harness({"w1": 0.9}, {"w1": 0.8})

        harness.score("w1", "w1")

        entry = recorder.entries[0]
        assert entry.active_score == 0.8
        assert entry.active_model_id == "flownet@1.0.0"

    def test_both_models_score_the_same_window(self) -> None:
        shadow = _FixedScorer("flownet@2.0.0", {"w1": 0.9})
        active = _FixedScorer("flownet@1.0.0", {"w1": 0.8})
        harness = ShadowHarness(shadow, InMemoryShadowRecorder(), active=active)

        harness.score("w1", "w1")

        assert shadow.scored == ["w1"]
        assert active.scored == ["w1"]

    def test_without_an_active_model_the_pair_fields_are_none(self) -> None:
        harness, recorder = _harness({"w1": 0.9})

        harness.score("w1", "w1")

        entry = recorder.entries[0]
        assert entry.active_score is None
        assert entry.active_model_id is None


class TestNoAlertsAreProduced:
    """The second half, and the one that has to hold absolutely."""

    def test_every_recorded_score_is_marked_not_alerted(self) -> None:
        harness, recorder = _harness({"w1": 0.99, "w2": 1.0, "w3": 0.75})

        harness.score_all([("w1", "w1"), ("w2", "w2"), ("w3", "w3")])

        assert all(not entry.alerted for entry in recorder.entries)

    def test_a_score_far_above_the_threshold_still_alerts_nothing(self) -> None:
        """The whole point: a confident detection changes nothing in shadow mode."""
        harness, recorder = _harness({"w1": 1.0}, alert_threshold=0.5)

        entry = harness.score("w1", "w1")

        assert entry.score == 1.0
        assert entry.alerted is False

    def test_the_harness_accepts_no_alert_sink(self) -> None:
        """Structural: there is no parameter through which one could be passed."""
        parameters = set(inspect.signature(ShadowHarness.__init__).parameters)

        assert not parameters & {
            "alert_sink",
            "alerts",
            "publisher",
            "sink",
            "on_alert",
            "alert_publisher",
        }

    def test_the_harness_exposes_no_publishing_method(self) -> None:
        """Structural: nothing on the class can emit an alert."""
        public = {name for name in dir(ShadowHarness) if not name.startswith("_")}
        publishing = {
            name
            for name in public
            if any(word in name.lower() for word in ("publish", "alert", "notify", "emit"))
        }

        assert publishing == set()

    def test_a_spy_on_the_alert_path_sees_nothing(self) -> None:
        """End to end: an alert sink exists in the process and is never reached."""
        sink = _SpyAlertSink()
        harness, recorder = _harness({"w1": 1.0, "w2": 0.9, "w3": 0.8})

        harness.score_all([("w1", "w1"), ("w2", "w2"), ("w3", "w3")])

        assert len(recorder.entries) == 3
        assert sink.published == []

    def test_the_shadow_score_type_cannot_carry_an_alert(self) -> None:
        """The record has one boolean and it is always False."""
        fields = set(ShadowScore.__slots__)

        assert fields == {
            "window_id",
            "score",
            "shadow_model_id",
            "active_model_id",
            "active_score",
            "alerted",
        }


class TestDistributionsAreComparable:
    """The other half: comparable is a measurement, not an impression."""

    def test_identical_distributions_are_comparable(self) -> None:
        values = {f"w{i}": i / 20 for i in range(20)}
        harness = _scored(values, dict(values))

        comparison = harness.compare()

        assert comparison.comparable
        assert comparison.psi == pytest.approx(0.0, abs=1e-9)
        assert comparison.band == "stable"
        assert comparison.pairs == 20

    def test_a_shifted_distribution_is_not_comparable(self) -> None:
        """Every shadow score above every active score must be caught."""
        active = {f"w{i}": i / 100 for i in range(40)}
        shadow = {key: value + 0.9 for key, value in active.items()}
        harness = _scored(shadow, active)

        comparison = harness.compare()

        assert not comparison.comparable
        assert comparison.band == "significant"

    def test_the_reference_is_the_active_model(self) -> None:
        """The question is whether the new model looks like the old one."""
        harness = _scored({"w1": 0.5, "w2": 0.5}, {"w1": 0.5, "w2": 0.5})

        comparison = harness.compare()

        assert comparison.psi >= 0.0

    def test_disagreement_is_reported_even_when_distributions_match(self) -> None:
        """Two models can agree on distribution and disagree on every window."""
        active = {f"w{i}": 0.9 for i in range(5)}
        shadow = {f"w{i}": 0.1 for i in range(5)}
        harness = _scored(shadow, active)

        comparison = harness.compare()

        assert comparison.disagreement_rate == 1.0
        assert comparison.active_alerts == 5
        assert comparison.shadow_alerts == 0

    def test_agreeing_models_have_no_disagreement(self) -> None:
        values = {f"w{i}": 0.9 for i in range(5)}
        harness = _scored(values, dict(values))

        assert harness.compare().disagreement_rate == 0.0

    def test_alert_counts_respect_the_threshold(self) -> None:
        active = {"w1": 0.4, "w2": 0.6}
        shadow = {"w1": 0.3, "w2": 0.8}
        harness = _scored(shadow, active, alert_threshold=0.5)

        comparison = harness.compare()

        assert comparison.active_alerts == 1
        assert comparison.shadow_alerts == 1

    def test_a_custom_threshold_is_honoured(self) -> None:
        values = {f"w{i}": i / 20 for i in range(20)}
        shifted = {key: min(value + 0.15, 1.0) for key, value in values.items()}
        harness = _scored(shifted, values)

        lenient = harness.compare(threshold=100.0)
        strict = harness.compare(threshold=1e-9)

        assert lenient.comparable
        assert not strict.comparable

    def test_entries_can_be_supplied_explicitly(self) -> None:
        """An offline comparison of previously recorded entries.

        An active model is still required: the refusal to compare against nothing
        is deliberately strict, so a harness that has no incumbent cannot be told
        its shadow distribution is comparable even when handed scores by hand.
        """
        harness, _ = _harness({"w1": 0.5, "w2": 0.5}, {"w1": 0.5, "w2": 0.5})
        entries = [
            ShadowScore(
                window_id="w1",
                score=0.5,
                shadow_model_id="s",
                active_model_id="a",
                active_score=0.5,
            ),
            ShadowScore(
                window_id="w2",
                score=0.5,
                shadow_model_id="s",
                active_model_id="a",
                active_score=0.5,
            ),
        ]

        assert harness.compare(entries).pairs == 2

    def test_unpaired_entries_are_excluded(self) -> None:
        """A window the incumbent never scored cannot contribute to a pairing."""
        harness, _ = _harness({"w1": 0.5, "w2": 0.5, "w3": 0.5}, {"w1": 0.5, "w2": 0.5, "w3": 0.5})
        paired = [
            ShadowScore(
                window_id=key,
                score=0.5,
                shadow_model_id="s",
                active_model_id="a",
                active_score=0.5,
            )
            for key in ("w1", "w2", "w3")
        ]
        unpaired = ShadowScore(
            window_id="w4",
            score=0.9,
            shadow_model_id="s",
            active_model_id=None,
            active_score=None,
        )

        comparison = harness.compare([*paired, unpaired])

        assert comparison.pairs == 3

    def test_a_window_the_incumbent_cannot_score_is_an_error_not_a_gap(self) -> None:
        """Silently dropping an unscorable window would bias the comparison."""
        harness, _ = _harness({"w1": 0.5, "w2": 0.5}, {"w1": 0.5})

        with pytest.raises(KeyError):
            harness.score("w2", "w2")


class TestComparisonRefusals:
    """A comparison against nothing must not be reported as comparable."""

    def test_refuses_with_no_active_model(self) -> None:
        harness, _ = _harness({"w1": 0.5, "w2": 0.5})

        with pytest.raises(ValueError, match="no active model is configured"):
            harness.compare()

    def test_refuses_fewer_than_two_paired_scores(self) -> None:
        harness, _ = _harness({"w1": 0.5}, {"w1": 0.5})

        harness.score("w1", "w1")

        with pytest.raises(ValueError, match="at least 2 paired scores"):
            harness.compare()

    def test_refuses_when_the_recorder_hides_its_entries(self) -> None:
        class _Opaque:
            def record(self, entry: ShadowScore) -> None:
                del entry

        harness = ShadowHarness(
            _FixedScorer("s", {"w1": 0.5}), _Opaque(), active=_FixedScorer("a", {"w1": 0.5})
        )

        with pytest.raises(ValueError, match="recorder does not expose"):
            harness.compare()

    def test_serialises(self) -> None:
        values = {f"w{i}": i / 20 for i in range(20)}
        harness = _scored(values, dict(values))

        payload = harness.compare().as_json()

        assert set(payload) == {
            "psi",
            "band",
            "comparable",
            "threshold",
            "pairs",
            "disagreement_rate",
            "alert_threshold",
            "shadow_alerts",
            "active_alerts",
        }


class TestIdentity:
    """The harness has to say which model is shadowing."""

    def test_reports_the_shadow_model_id(self) -> None:
        harness, _ = _harness({"w1": 0.5})

        assert harness.shadow_model_id == "flownet@2.0.0"
