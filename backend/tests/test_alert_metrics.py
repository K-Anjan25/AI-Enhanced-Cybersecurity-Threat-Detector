"""PRD section 8 alert metrics are recorded by the correlator.

Before this change ``aegis_alerts_created_total`` and ``aegis_score_latency_seconds``
were declared but never incremented, so any dashboard built on them showed nothing.
These tests read the Prometheus registry itself, because a counter that is declared
but not incremented passes every check that only reads the metric object.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aegis_ml.scoring.fusion import fuse
from app.services.correlator import Correlator, Detection, InMemoryCaseStore, Modality
from prometheus_client import REGISTRY

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _detection(*, entity_id: int, evidence: str, at: datetime = NOW) -> Detection:
    return Detection(
        entity_id=entity_id,
        family="Reconnaissance",
        modality=Modality.flow,
        score=0.8,
        at=at,
        evidence_id=evidence,
        model_id="flownet@1.0.0",
        explanation=None,
        traceparent=None,
    )


def _sample(name: str, labels: dict[str, str] | None = None) -> float:
    value = REGISTRY.get_sample_value(name, labels or {})
    return 0.0 if value is None else value


def _alerts_total() -> float:
    return sum(
        _sample("aegis_alerts_created_total", {"severity": s})
        for s in ("info", "low", "medium", "high", "critical")
    )


def test_a_new_alert_increments_the_counter_and_observes_latency() -> None:
    correlator = Correlator(InMemoryCaseStore(), fuse)
    before_total = _alerts_total()
    before_count = _sample("aegis_detection_to_alert_seconds_count")

    outcome = correlator.ingest(_detection(entity_id=101, evidence="flow:a@1"))

    assert outcome.action.value == "created"
    assert _alerts_total() == before_total + 1
    assert _sample("aegis_detection_to_alert_seconds_count") == before_count + 1


def test_a_duplicate_inside_the_cool_down_is_not_a_new_alert() -> None:
    correlator = Correlator(InMemoryCaseStore(), fuse)
    correlator.ingest(_detection(entity_id=202, evidence="flow:b@1"))
    before_count = _sample("aegis_detection_to_alert_seconds_count")

    outcome = correlator.ingest(_detection(entity_id=202, evidence="flow:b@2"))

    assert outcome.action.value != "created"
    assert _sample("aegis_detection_to_alert_seconds_count") == before_count
