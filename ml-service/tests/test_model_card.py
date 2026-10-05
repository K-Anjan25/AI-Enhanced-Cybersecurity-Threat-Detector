r"""Tests for the model card (T-214, R-74).

The property under test is that a number cannot reach a card without a recorded
run behind it. The most important tests are therefore the refusals: a card that
silently accepted a typed-in number would be indistinguishable from a correct one
until someone tried to reproduce it.
"""

from __future__ import annotations

import json

import pytest
from aegis_ml.registry.model_card import (
    DEFAULT_ADVERSARIAL_CAVEAT,
    CardError,
    MetricNotFound,
    ModelCard,
    SourcedMetric,
    build_card,
    load_metric,
)

SAMPLE_RUN = {
    "task": "T-208",
    "recall": 0.7955,
    "precision": 0.5904,
    "roc_auc": 0.7464,
    "passed": True,
    "target": {"attack_windows": 2562, "windows": 6415},
    "latency_ms": {"p95": 22.59},
    "note": "measured, not estimated",
}


@pytest.fixture
def run_artifact(tmp_path: object) -> str:
    """A recorded run on disk, shaped like the real transfer artifact."""
    from pathlib import Path

    target = Path(str(tmp_path)) / "transfer.json"
    target.write_text(json.dumps(SAMPLE_RUN), encoding="utf-8")
    return str(target)


class TestMetricsMustBeSourced:
    """There is no way to build a metric from a number alone."""

    def test_an_metric_without_an_artifact_is_refused(self) -> None:
        with pytest.raises(CardError, match="no artifact"):
            SourcedMetric(name="recall", value=0.98, artifact="", field="recall")

    def test_a_metric_without_a_field_path_is_refused(self) -> None:
        with pytest.raises(CardError, match="no field path"):
            SourcedMetric(name="recall", value=0.98, artifact="run.json", field="")

    def test_a_metric_without_a_name_is_refused(self) -> None:
        with pytest.raises(CardError, match="needs a name"):
            SourcedMetric(name="  ", value=0.98, artifact="run.json", field="recall")

    def test_a_non_numeric_value_is_refused(self) -> None:
        with pytest.raises(CardError, match="non-numeric"):
            SourcedMetric(name="recall", value="high", artifact="run.json", field="recall")  # type: ignore[arg-type]

    def test_a_boolean_is_refused_even_though_bool_is_an_int(self) -> None:
        """`isinstance(True, int)` is True in Python, which would slip past a naive check."""
        with pytest.raises(CardError, match="non-numeric"):
            SourcedMetric(name="passed", value=True, artifact="run.json", field="passed")  # type: ignore[arg-type]

    def test_a_non_finite_value_is_refused(self) -> None:
        for bad in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(CardError, match="not a number"):
                SourcedMetric(name="recall", value=bad, artifact="run.json", field="recall")

    def test_the_provenance_names_artifact_and_field(self) -> None:
        metric = SourcedMetric(name="recall", value=0.8, artifact="run.json", field="a.b")

        assert metric.provenance == "run.json → a.b"

    def test_rendering_puts_the_citation_beside_the_number(self) -> None:
        metric = SourcedMetric(name="recall", value=0.8, artifact="run.json", field="recall")

        rendered = metric.render()

        assert "0.8" in rendered
        assert "run.json → recall" in rendered


class TestLoadMetric:
    """The only sanctioned route from a file to a number."""

    def test_reads_a_top_level_number(self, run_artifact: str) -> None:
        metric = load_metric(run_artifact, "Transfer recall", "recall")

        assert metric.value == pytest.approx(0.7955)
        assert metric.field == "recall"
        assert metric.artifact == run_artifact

    def test_reads_a_nested_number(self, run_artifact: str) -> None:
        metric = load_metric(run_artifact, "Target attack windows", "target", "attack_windows")

        assert metric.value == 2562.0
        assert metric.field == "target.attack_windows"

    def test_the_value_comes_from_the_file_not_the_call(self, tmp_path: object) -> None:
        """The caller supplies no number, so it cannot supply a wrong one."""
        from pathlib import Path

        target = Path(str(tmp_path)) / "run.json"
        target.write_text(json.dumps({"recall": 0.4242}), encoding="utf-8")

        assert load_metric(target, "recall", "recall").value == pytest.approx(0.4242)


class TestLoadMetricRefusals:
    """Citing something that is not there is the R-74 failure to catch."""

    def test_a_missing_field_is_refused(self, run_artifact: str) -> None:
        with pytest.raises(MetricNotFound, match="has no such field"):
            load_metric(run_artifact, "F1", "f1")

    def test_a_missing_nested_field_is_refused(self, run_artifact: str) -> None:
        with pytest.raises(MetricNotFound, match="has no such field"):
            load_metric(run_artifact, "p99", "latency_ms", "p99")

    def test_walking_into_a_non_object_is_refused(self, run_artifact: str) -> None:
        with pytest.raises(MetricNotFound, match="has no such field"):
            load_metric(run_artifact, "nonsense", "recall", "deeper")

    def test_a_non_numeric_field_is_refused(self, run_artifact: str) -> None:
        with pytest.raises(MetricNotFound, match="rather than a number"):
            load_metric(run_artifact, "note", "note")

    def test_a_boolean_field_is_refused_as_a_metric(self, run_artifact: str) -> None:
        with pytest.raises(MetricNotFound, match="rather than a number"):
            load_metric(run_artifact, "passed", "passed")

    def test_a_missing_artifact_is_reported_as_missing(self) -> None:
        """Distinct from a bad field: the run itself was never recorded."""
        with pytest.raises(FileNotFoundError, match="no recorded run"):
            load_metric("/nonexistent/run.json", "recall", "recall")


class TestCardRefusals:
    """A card that would mislead by omission is not emitted."""

    def _card(self, **overrides: object) -> ModelCard:
        metric = SourcedMetric(name="recall", value=0.8, artifact="run.json", field="recall")
        arguments: dict[str, object] = {
            "model_id": "flownet@1.0.0",
            "kind": "flow",
            "intended_use": "Rank network windows for triage.",
            "metrics": (metric,),
            "limitations": ("Evaluated on one capture.",),
            "adversarial_caveat": DEFAULT_ADVERSARIAL_CAVEAT,
        }
        arguments.update(overrides)
        return build_card(**arguments)  # type: ignore[arg-type]

    def test_a_card_with_no_metrics_is_refused(self) -> None:
        with pytest.raises(CardError, match="no metrics"):
            self._card(metrics=())

    def test_a_card_with_no_limitations_is_refused(self) -> None:
        with pytest.raises(CardError, match="at least one limitation"):
            self._card(limitations=())

    def test_a_card_with_no_adversarial_caveat_is_refused(self) -> None:
        """T-214 requires it, and omitting it implies a robustness nothing here has."""
        with pytest.raises(CardError, match="adversarial-evasion caveat is required"):
            self._card(adversarial_caveat="   ")

    def test_a_card_with_no_intended_use_is_refused(self) -> None:
        with pytest.raises(CardError, match="intended use"):
            self._card(intended_use="")

    def test_a_card_with_no_model_id_is_refused(self) -> None:
        with pytest.raises(CardError, match="needs a model id"):
            self._card(model_id="  ")

    def test_a_card_cannot_describe_latest(self) -> None:
        """R-68 forbids the id, so a card naming it would describe nothing."""
        with pytest.raises(CardError, match="R-68"):
            self._card(model_id="latest")

    def test_a_plain_dict_cannot_be_substituted_for_a_metric(self) -> None:
        """The check that stops a JSON round-trip smuggling numbers back in."""
        with pytest.raises(CardError, match="not a SourcedMetric"):
            build_card(
                model_id="flownet@1.0.0",
                kind="flow",
                intended_use="triage",
                metrics=[{"name": "recall", "value": 0.99}],  # type: ignore[list-item]
                limitations=("one capture.",),
            )

    def test_a_bare_float_cannot_be_substituted_either(self) -> None:
        with pytest.raises(CardError, match="not a SourcedMetric"):
            build_card(
                model_id="flownet@1.0.0",
                kind="flow",
                intended_use="triage",
                metrics=[0.99],  # type: ignore[list-item]
                limitations=("one capture.",),
            )


class TestRendering:
    """The rendered card has to show its sources, not just its numbers."""

    def test_every_metric_line_carries_its_provenance(self, run_artifact: str) -> None:
        card = build_card(
            model_id="flownet@1.0.0",
            kind="flow",
            intended_use="Rank network windows for triage.",
            metrics=[
                load_metric(run_artifact, "Transfer recall", "recall"),
                load_metric(run_artifact, "Scoring p95 (ms)", "latency_ms", "p95"),
            ],
            limitations=("Evaluated on one capture.",),
        )

        markdown = card.as_markdown()

        assert "0.7955" in markdown
        assert "22.59" in markdown
        assert f"{run_artifact} → recall" in markdown
        assert f"{run_artifact} → latency_ms.p95" in markdown

    def test_the_required_sections_are_present(self, run_artifact: str) -> None:
        card = build_card(
            model_id="flownet@1.0.0",
            kind="flow",
            intended_use="Triage.",
            metrics=[load_metric(run_artifact, "recall", "recall")],
            limitations=("one capture.",),
        )

        markdown = card.as_markdown()

        for heading in (
            "## Intended use",
            "## Metrics",
            "## Limitations",
            "## Adversarial evasion",
        ):
            assert heading in markdown

    def test_the_caveat_appears_verbatim(self, run_artifact: str) -> None:
        card = build_card(
            model_id="flownet@1.0.0",
            kind="flow",
            intended_use="Triage.",
            metrics=[load_metric(run_artifact, "recall", "recall")],
            limitations=("one capture.",),
        )

        assert DEFAULT_ADVERSARIAL_CAVEAT in card.as_markdown()

    def test_serialises_and_lists_every_artifact_cited(self, run_artifact: str) -> None:
        card = build_card(
            model_id="flownet@1.0.0",
            kind="flow",
            intended_use="Triage.",
            metrics=[
                load_metric(run_artifact, "recall", "recall"),
                load_metric(run_artifact, "precision", "precision"),
            ],
            limitations=("one capture.",),
        )

        payload = card.as_json()

        assert payload["artifacts_cited"] == [run_artifact]
        assert len(payload["metrics"]) == 2  # type: ignore[arg-type]

    def test_the_default_caveat_is_substantive(self) -> None:
        """A caveat that only says "may be evaded" tells an operator nothing."""
        assert len(DEFAULT_ADVERSARIAL_CAVEAT) > 200
        for concept in ("evade", "padding", "recall"):
            assert concept in DEFAULT_ADVERSARIAL_CAVEAT


class TestEndToEnd:
    """The whole path from a recorded run to a card, with no number typed in."""

    def test_a_card_built_entirely_from_a_run_artifact(self, tmp_path: object) -> None:
        from pathlib import Path

        target = Path(str(tmp_path)) / "run.json"
        target.write_text(
            json.dumps({"recall": 0.7955, "roc_auc": 0.7464, "latency_ms": {"p95": 22.59}}),
            encoding="utf-8",
        )

        card = build_card(
            model_id="flownet@1.0.0",
            kind="flow",
            intended_use="Rank windows for triage on networks resembling the evaluation capture.",
            metrics=[
                load_metric(target, "Transfer recall", "recall"),
                load_metric(target, "Transfer ROC-AUC", "roc_auc"),
                load_metric(target, "Scoring p95 (ms)", "latency_ms", "p95"),
            ],
            limitations=(
                "Evaluated on one pair of captures; cross-capture transfer failed R-66 "
                "at the supervised head and only passes on reconstruction error.",
                "Precision 0.5904 against a 40% attack base rate is near chance.",
            ),
        )

        markdown = card.as_markdown()

        assert "0.7955" in markdown
        assert "22.59" in markdown
        # No number appears in the card that is not cited.
        for metric in card.metrics:
            assert f"{metric.value:g}" in markdown
