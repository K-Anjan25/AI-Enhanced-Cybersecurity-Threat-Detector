"""Response-time metrics must be measured, bounded, and honest about limits."""

from datetime import datetime, timedelta, timezone

from app.models import SecurityAlert
from app.models.case import Case
from app.services import response_metrics

ORG = 1


def _t(minutes_ago: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)


def _pair(db, *, ingest_min_ago: float, triage_min_ago: float, decided_min_ago=None,
          decision="approved"):
    """One alert plus the case raised from it, with explicit timings."""
    alert = SecurityAlert(
        org_id=ORG, severity="HIGH", source="edr", message="evt",
        created_at=_t(ingest_min_ago),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    case = Case(
        org_id=ORG, title="c", kind="analyst", source_alert_id=alert.id,
        created_at=_t(triage_min_ago),
        decision=decision if decided_min_ago is not None else "pending",
        decided_at=_t(decided_min_ago) if decided_min_ago is not None else None,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return alert, case


def _metric(report, name):
    return next(m for m in report["metrics"] if m["metric"] == name)


# ---------------------------------------------------------------------------
# The numbers are real
# ---------------------------------------------------------------------------

def test_time_to_triage_is_measured_from_timestamps(db_session):
    # Ingested 30 min ago, triaged 20 min ago -> 10 minutes.
    _pair(db_session, ingest_min_ago=30, triage_min_ago=20)
    report = response_metrics.compute(db_session, ORG)

    triage = _metric(report, "time_to_triage")
    assert triage["sample_size"] == 1
    assert abs(triage["median_minutes"] - 10.0) < 0.5


def test_time_to_contain_spans_ingest_to_decision(db_session):
    _pair(db_session, ingest_min_ago=60, triage_min_ago=50, decided_min_ago=20)
    report = response_metrics.compute(db_session, ORG)

    assert abs(_metric(report, "time_to_decision")["median_minutes"] - 30.0) < 0.5
    assert abs(_metric(report, "time_to_contain")["median_minutes"] - 40.0) < 0.5


def test_median_and_p90_reflect_the_spread(db_session):
    for delay in (5, 10, 15, 20, 100):
        _pair(db_session, ingest_min_ago=200, triage_min_ago=200 - delay)
    triage = _metric(response_metrics.compute(db_session, ORG), "time_to_triage")

    assert triage["sample_size"] == 5
    assert abs(triage["median_minutes"] - 15.0) < 0.5
    assert triage["p90_minutes"] >= triage["median_minutes"]
    assert abs(triage["slowest_minutes"] - 100.0) < 0.5


# ---------------------------------------------------------------------------
# Nothing measured is never reported as zero
# ---------------------------------------------------------------------------

def test_empty_window_returns_none_not_zero(db_session):
    report = response_metrics.compute(db_session, ORG)
    for m in report["metrics"]:
        assert m["median_minutes"] is None, "0 minutes would read as 'instant'"
        assert m["sample_size"] == 0
        assert m["reliable"] is False
        assert m["reason"]


def test_pending_cases_do_not_contribute_a_decision_time(db_session):
    _pair(db_session, ingest_min_ago=30, triage_min_ago=20)  # never decided
    report = response_metrics.compute(db_session, ORG)

    assert _metric(report, "time_to_decision")["sample_size"] == 0
    assert _metric(report, "time_to_contain")["sample_size"] == 0
    assert report["open_backlog"]["undecided_cases"] == 1


def test_backlog_reports_the_oldest_undecided_case(db_session):
    _pair(db_session, ingest_min_ago=500, triage_min_ago=480)
    _pair(db_session, ingest_min_ago=100, triage_min_ago=90)
    backlog = response_metrics.compute(db_session, ORG)["open_backlog"]

    assert backlog["undecided_cases"] == 2
    assert backlog["oldest_undecided_minutes"] >= 470


# ---------------------------------------------------------------------------
# A small sample is flagged, not dressed up
# ---------------------------------------------------------------------------

def test_small_sample_is_marked_unreliable(db_session):
    _pair(db_session, ingest_min_ago=30, triage_min_ago=20)
    triage = _metric(response_metrics.compute(db_session, ORG), "time_to_triage")

    assert triage["sample_size"] == 1
    assert triage["reliable"] is False
    assert "5 needed" in triage["reason"]


def test_sufficient_sample_is_marked_reliable(db_session):
    for _ in range(5):
        _pair(db_session, ingest_min_ago=30, triage_min_ago=20)
    triage = _metric(response_metrics.compute(db_session, ORG), "time_to_triage")

    assert triage["sample_size"] == 5
    assert triage["reliable"] is True
    assert triage["reason"] is None


# ---------------------------------------------------------------------------
# The limits are stated, not hidden
# ---------------------------------------------------------------------------

def test_triage_metric_disclaims_being_a_true_mttd(db_session):
    triage = _metric(response_metrics.compute(db_session, ORG), "time_to_triage")
    assert "not a true MTTD" in triage["caveat"]
    assert triage["measures"] == "alert ingested → case raised"


def test_unmeasurable_metrics_are_named_with_reasons(db_session):
    report = response_metrics.compute(db_session, ORG)
    names = {n["metric"] for n in report["not_measured"]}

    # mean_time_to_detect moved out of this list once connectors began
    # recording event_time; what remains genuinely unmeasurable is the gap
    # before the source logged anything at all.
    assert {"dwell_time_before_logging", "cost_avoidance", "analyst_hours_saved"} <= names
    assert "mean_time_to_detect" not in names
    for entry in report["not_measured"]:
        assert entry["reason"]


def test_containment_metric_does_not_claim_verified_execution(db_session):
    contain = _metric(response_metrics.compute(db_session, ORG), "time_to_contain")
    assert "not confirmation" in contain["caveat"]


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_negative_intervals_are_discarded(db_session):
    """Backdated rows must not drag an average below zero."""
    # Case created *before* its alert — clock skew or a backfill.
    _pair(db_session, ingest_min_ago=10, triage_min_ago=60)
    triage = _metric(response_metrics.compute(db_session, ORG), "time_to_triage")
    assert triage["sample_size"] == 0


def test_cases_outside_the_window_are_excluded(db_session):
    _pair(db_session, ingest_min_ago=60 * 24 * 90, triage_min_ago=60 * 24 * 89)
    report = response_metrics.compute(db_session, ORG, window_days=30)
    assert report["cases_in_window"] == 0


def test_scales_to_hundreds_of_cases(db_session):
    for i in range(250):
        _pair(
            db_session,
            ingest_min_ago=1000 + i,
            triage_min_ago=1000 + i - (i % 30) - 1,
            decided_min_ago=100,
        )
    report = response_metrics.compute(db_session, ORG)

    triage = _metric(report, "time_to_triage")
    assert triage["sample_size"] == 250
    assert triage["reliable"] is True
    assert triage["median_minutes"] > 0
    assert triage["fastest_minutes"] <= triage["median_minutes"] <= triage["slowest_minutes"]


# ---------------------------------------------------------------------------
# The fabricated figures are gone
# ---------------------------------------------------------------------------

def test_exec_risk_no_longer_reports_a_hardcoded_mttd(db_session):
    from app.services import exec_risk_service

    _pair(db_session, ingest_min_ago=30, triage_min_ago=20)
    metrics = exec_risk_service.calculate_risk_metrics(db_session, ORG)
    names = {m.metric_name for m in metrics}

    assert "mean_time_to_detect_hours" not in names, "2.5 hours was a literal"
    triage = next(m for m in metrics if m.metric_name == "median_time_to_triage_minutes")
    assert abs(triage.metric_value - 10.0) < 0.5


def test_roi_no_longer_invents_dollars_or_hours(db_session):
    from app.services import exec_risk_service

    roi = exec_risk_service.calculate_roi(db_session, ORG)
    blob = str(roi)

    assert "50000" not in blob, "$50,000 cost avoidance was invented"
    assert "analyst_hours_saved" not in {c["metric_name"] for c in roi["counted"]}
    assert {n["metric"] for n in roi["not_measured"]} >= {"cost_avoidance", "analyst_hours_saved"}


def test_board_pack_carries_measured_times_not_invented_roi(db_session):
    from app.services import exec_risk_service

    report = exec_risk_service.generate_board_pack(db_session, ORG)
    data = report.report_json

    assert "roi" not in data
    assert "response_times" in data
    assert "not_measured" in data


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_response_times_endpoint(client, admin_headers):
    r = client.get("/api/v1/exec-risk/response-times", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["window_days"] == 30
    assert {m["metric"] for m in body["metrics"]} == {
        "time_to_detect", "time_to_triage", "time_to_decision", "time_to_contain",
    }


def test_response_times_window_is_bounded(client, admin_headers):
    r = client.get("/api/v1/exec-risk/response-times?window_days=99999", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["window_days"] == 365
