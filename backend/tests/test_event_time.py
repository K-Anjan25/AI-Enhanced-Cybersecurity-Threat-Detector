"""Source event times: parsed strictly, stored honestly, or left NULL.

Detection latency is computed from `SecurityAlert.event_time`, so a wrong
value here silently corrupts the headline metric. These tests pin that a
timestamp is either parsed correctly or rejected — never guessed.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import SecurityAlert
from app.models.case import Case
from app.services import response_metrics
from app.services.connector_service import (
    _coerce_event_time,
    _extract_event_time,
    _normalize_azuread_event,
    _normalize_event,
    _normalize_github_alert,
    _normalize_gworkspace_event,
    _normalize_slack_audit_event,
)

ORG = 1


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected_iso",
    [
        ("2026-08-30T07:15:00Z", "2026-08-30T07:15:00+00:00"),
        ("2026-08-30T07:15:00+00:00", "2026-08-30T07:15:00+00:00"),
        # Naive input is treated as UTC, not host-local: assuming local time
        # would shift every metric by the server's offset.
        ("2026-08-30T07:15:00", "2026-08-30T07:15:00+00:00"),
        (1756530000, "2025-08-30T05:00:00+00:00"),
        ("1756530000", "2025-08-30T05:00:00+00:00"),
        # Milliseconds must not be read as seconds (would land in year 57000).
        (1756530000000, "2025-08-30T05:00:00+00:00"),
    ],
)
def test_recognised_formats_parse_to_utc(value, expected_iso):
    assert _coerce_event_time(value).isoformat() == expected_iso


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "not-a-date",
        0,                       # epoch zero is a null sentinel, not 1970
        -1,
        True,                    # bool is an int subclass; must not become 1970
        "9999-01-01T00:00:00Z",  # far-future sentinel
        "1970-01-01T00:00:00Z",  # pre-2000 floor
        {},
        [],
    ],
)
def test_unusable_values_are_rejected_not_guessed(value):
    assert _coerce_event_time(value) is None


def test_future_timestamps_beyond_tolerance_are_rejected():
    far_future = datetime.now(timezone.utc) + timedelta(days=30)
    assert _coerce_event_time(far_future.isoformat()) is None


def test_slight_clock_skew_into_the_future_is_tolerated():
    """A source a few minutes ahead is normal; discarding it would lose data."""
    skewed = datetime.now(timezone.utc) + timedelta(minutes=5)
    assert _coerce_event_time(skewed.isoformat()) is not None


# ---------------------------------------------------------------------------
# Provider field mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload",
    [
        {"date_create": 1756530000},                        # Slack
        {"activityDateTime": "2026-08-30T07:15:00Z"},       # Graph auditLogs
        {"createdDateTime": "2026-08-30T07:15:00Z"},        # Graph signIns
        {"created_at": "2026-08-30T07:15:00Z"},             # GitHub
        {"@timestamp": "2026-08-30T07:15:00Z"},             # Elastic
        {"timestamp": "2026-08-30T07:15:00Z"},              # generic
    ],
)
def test_each_provider_field_is_recognised(payload):
    assert _extract_event_time(payload) is not None


def test_first_parseable_field_wins_over_later_junk():
    got = _extract_event_time(
        {"event_time": "2026-08-30T07:15:00Z", "timestamp": "garbage"}
    )
    assert got.isoformat() == "2026-08-30T07:15:00+00:00"


def test_unparseable_first_field_falls_through_to_a_good_one():
    got = _extract_event_time({"created_at": "garbage", "timestamp": 1756530000})
    assert got is not None


def test_payload_with_no_time_yields_none():
    assert _extract_event_time({"message": "something happened"}) is None


# ---------------------------------------------------------------------------
# Normalisers carry it through
# ---------------------------------------------------------------------------

def test_all_normalizers_emit_an_event_time_key():
    cases = [
        _normalize_github_alert({"rule": {"description": "x"}, "created_at": "2026-08-30T07:15:00Z"}),
        _normalize_slack_audit_event({"action": "login", "date_create": 1756530000}),
        _normalize_gworkspace_event({"actor": {"email": "a@b.c"}, "id": {}, "timestamp": "2026-08-30T07:15:00Z"}),
        _normalize_azuread_event({"userPrincipalName": "a@b.c", "activityDateTime": "2026-08-30T07:15:00Z"}),
        _normalize_event({"message": "m", "severity": "HIGH", "timestamp": "2026-08-30T07:15:00Z"}),
    ]
    for normalized in cases:
        assert normalized is not None
        assert "event_time" in normalized, normalized
        assert normalized["event_time"] is not None


def test_normalizer_leaves_event_time_none_when_absent():
    normalized = _normalize_event({"message": "m", "severity": "HIGH"})
    assert normalized["event_time"] is None


# ---------------------------------------------------------------------------
# The metric
# ---------------------------------------------------------------------------

def _alert(db, *, event_min_ago=None, ingest_min_ago=10):
    now = datetime.now(timezone.utc)
    alert = SecurityAlert(
        org_id=ORG, severity="HIGH", source="edr", message="e",
        created_at=now - timedelta(minutes=ingest_min_ago),
        event_time=(now - timedelta(minutes=event_min_ago)) if event_min_ago else None,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    case = Case(
        org_id=ORG, title="c", kind="analyst", source_alert_id=alert.id,
        created_at=now - timedelta(minutes=max(0, ingest_min_ago - 2)),
    )
    db.add(case)
    db.commit()
    return alert


def _detect(report):
    return next(m for m in report["metrics"] if m["metric"] == "time_to_detect")


def test_detection_latency_is_measured_from_the_event(db_session):
    # Happened 40 min ago, ingested 10 min ago -> 30 minutes of latency.
    _alert(db_session, event_min_ago=40, ingest_min_ago=10)
    detect = _detect(response_metrics.compute(db_session, ORG))

    assert detect["sample_size"] == 1
    assert abs(detect["median_minutes"] - 30.0) < 0.5


def test_alerts_without_an_event_time_are_excluded_not_zeroed(db_session):
    """The critical case: a missing time must not read as instant detection."""
    _alert(db_session, event_min_ago=60, ingest_min_ago=10)   # 50 min latency
    for _ in range(3):
        _alert(db_session, event_min_ago=None, ingest_min_ago=10)  # no time

    detect = _detect(response_metrics.compute(db_session, ORG))

    assert detect["sample_size"] == 1, "unmeasurable alerts must not join the sample"
    assert abs(detect["median_minutes"] - 50.0) < 0.5, (
        "counting the three unmeasurable alerts as 0 would drag the median to 0"
    )


def test_caveat_states_how_much_of_the_window_was_measurable(db_session):
    _alert(db_session, event_min_ago=40)
    _alert(db_session, event_min_ago=None)
    detect = _detect(response_metrics.compute(db_session, ORG))

    assert "1 of 2 alert(s)" in detect["caveat"]
    assert "excluded rather than counted as zero" in detect["caveat"]


def test_no_event_times_at_all_says_so(db_session):
    _alert(db_session, event_min_ago=None)
    detect = _detect(response_metrics.compute(db_session, ORG))

    assert detect["sample_size"] == 0
    assert detect["median_minutes"] is None
    assert "No alerts in this window carried a source event time" in detect["caveat"]


def test_event_time_after_ingest_is_discarded(db_session):
    """Clock skew: an event stamped later than we received it is unusable."""
    now = datetime.now(timezone.utc)
    alert = SecurityAlert(
        org_id=ORG, severity="HIGH", source="edr", message="e",
        created_at=now - timedelta(minutes=60),
        event_time=now - timedelta(minutes=10),  # after ingest
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    db_session.add(
        Case(org_id=ORG, title="c", kind="analyst", source_alert_id=alert.id,
             created_at=now - timedelta(minutes=55))
    )
    db_session.commit()

    assert _detect(response_metrics.compute(db_session, ORG))["sample_size"] == 0


def test_mttd_no_longer_listed_as_unmeasurable(db_session):
    report = response_metrics.compute(db_session, ORG)
    names = {n["metric"] for n in report["not_measured"]}
    assert "mean_time_to_detect" not in names
    # The honest residual: we cannot see before the source logged anything.
    assert "dwell_time_before_logging" in names
