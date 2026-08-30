"""Confidence must be explainable, reproducible, and honest about blind spots."""

from app.models import Asset, SecurityAlert
from app.models.case import Case
from app.services import verdict_reasoning

ORG = 1


def _case(db, **kw):
    case = Case(org_id=ORG, title=kw.pop("title", "Suspicious login"), kind="analyst", **kw)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def _alert(db, **kw):
    kw.setdefault("severity", "HIGH")
    kw.setdefault("source", "edr")
    kw.setdefault("message", "suspicious process")
    alert = SecurityAlert(org_id=ORG, **kw)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


# ---------------------------------------------------------------------------
# The arithmetic must be checkable by hand
# ---------------------------------------------------------------------------

def test_confidence_equals_base_plus_contributions(db_session):
    alert = _alert(db_session, source_ip="203.0.113.9")
    case = _case(db_session, source_alert_id=alert.id)

    r = verdict_reasoning.explain(db_session, case)
    expected = r["base"] + sum(s["contribution"] for s in r["signals"])

    # Only equal when the coverage cap did not bite; assert the cap instead.
    if r["capped"]:
        assert r["confidence"] == r["confidence_cap"]
    else:
        assert abs(r["confidence"] - expected) < 0.001


def test_no_signals_stays_near_baseline_and_says_so(db_session):
    case = _case(db_session)
    r = verdict_reasoning.explain(db_session, case)

    assert r["signals"] == []
    assert r["confidence"] <= 0.50, "no evidence must not produce a confident verdict"
    assert "No corroborating signal" in r["summary"]


# ---------------------------------------------------------------------------
# Unavailable is recorded, never silently treated as clean
# ---------------------------------------------------------------------------

def test_every_unconsulted_signal_is_named_with_a_reason(db_session):
    case = _case(db_session)
    r = verdict_reasoning.explain(db_session, case)

    names = {u["signal"] for u in r["unavailable"]}
    assert {"crown_jewel_reach", "affected_assets", "threat_intel", "posture"} <= names
    for entry in r["unavailable"]:
        assert entry["reason"], f"{entry['signal']} must explain why it is unavailable"


def test_empty_inventory_is_distinguished_from_no_path_found(db_session):
    """"No assets recorded" and "no path exists" are different facts."""
    case = _case(db_session)
    r = verdict_reasoning.explain(db_session, case)
    reason = next(u["reason"] for u in r["unavailable"] if u["signal"] == "crown_jewel_reach")
    assert "no assets are recorded" in reason

    db_session.add(Asset(org_id=ORG, name="fs01", asset_type="host", criticality=3))
    db_session.commit()

    r2 = verdict_reasoning.explain(db_session, case)
    reason2 = next(u["reason"] for u in r2["unavailable"] if u["signal"] == "crown_jewel_reach")
    assert "no recorded attack path" in reason2


def test_missing_source_alert_is_reported_not_assumed(db_session):
    case = _case(db_session)
    r = verdict_reasoning.explain(db_session, case)
    reason = next(u["reason"] for u in r["unavailable"] if u["signal"] == "threat_intel")
    assert "no source alert" in reason


def test_disabled_threat_intel_is_reported_as_unavailable(db_session, monkeypatch):
    from app.services import threat_intel_enrichment

    monkeypatch.setattr(threat_intel_enrichment.settings, "THREAT_INTEL_ENABLED", False, raising=False)
    alert = _alert(db_session, source_ip="203.0.113.9")
    case = _case(db_session, source_alert_id=alert.id)

    r = verdict_reasoning.explain(db_session, case)
    reason = next(u["reason"] for u in r["unavailable"] if u["signal"] == "threat_intel")
    assert "THREAT_INTEL_ENABLED is false" in reason


# ---------------------------------------------------------------------------
# Signals derive from real rows
# ---------------------------------------------------------------------------

def test_threat_intel_raises_confidence_only_from_a_real_score(db_session):
    alert = _alert(
        db_session,
        source_ip="203.0.113.9",
        threat_intel={"risk_score": 90, "reasons": ["VT malicious 9"]},
    )
    case = _case(db_session, source_alert_id=alert.id)

    r = verdict_reasoning.explain(db_session, case)
    ti = next(s for s in r["signals"] if s["signal"] == "threat_intel")
    assert ti["contribution"] > 0
    assert ti["evidence"]["risk_score"] == 90
    assert "VT malicious 9" in ti["detail"]


def test_clean_threat_intel_lowers_confidence(db_session):
    """A clean lookup is evidence too — it should argue against the incident."""
    alert = _alert(db_session, source_ip="198.51.100.4", threat_intel={"risk_score": 0, "reasons": []})
    case = _case(db_session, source_alert_id=alert.id)

    r = verdict_reasoning.explain(db_session, case)
    ti = next(s for s in r["signals"] if s["signal"] == "threat_intel")
    assert ti["contribution"] < 0
    assert "clean" in ti["detail"].lower()


def test_correlation_counts_real_sibling_alerts(db_session):
    ip = "203.0.113.77"
    for _ in range(3):
        _alert(db_session, source_ip=ip)
    alert = _alert(db_session, source_ip=ip)
    case = _case(db_session, source_alert_id=alert.id)

    r = verdict_reasoning.explain(db_session, case)
    corr = next(s for s in r["signals"] if s["signal"] == "correlation")
    assert corr["evidence"]["related_alerts"] == 3
    assert corr["contribution"] > 0


def test_isolated_alert_slightly_reduces_confidence(db_session):
    alert = _alert(db_session, source_ip="203.0.113.200")
    case = _case(db_session, source_alert_id=alert.id)

    r = verdict_reasoning.explain(db_session, case)
    corr = next(s for s in r["signals"] if s["signal"] == "correlation")
    assert corr["evidence"]["related_alerts"] == 0
    assert corr["contribution"] < 0


# ---------------------------------------------------------------------------
# Confidence is bounded by how much was visible
# ---------------------------------------------------------------------------

def test_one_signal_cannot_produce_high_confidence(db_session):
    alert = _alert(
        db_session, source_ip="203.0.113.9", threat_intel={"risk_score": 100, "reasons": ["max"]}
    )
    case = _case(db_session, source_alert_id=alert.id)

    r = verdict_reasoning.explain(db_session, case)
    assert r["confidence"] <= 0.75, "thin evidence must not yield near-certainty"
    assert r["coverage"].startswith(f"{len(r['signals'])} of ")


def test_confidence_never_leaves_zero_to_one(db_session):
    alert = _alert(
        db_session, source_ip="203.0.113.9", threat_intel={"risk_score": 10_000, "reasons": []}
    )
    case = _case(db_session, source_alert_id=alert.id)
    r = verdict_reasoning.explain(db_session, case)
    assert 0.0 <= r["confidence"] <= 1.0


def test_contribution_is_capped_per_signal(db_session):
    alert = _alert(
        db_session, source_ip="203.0.113.9", threat_intel={"risk_score": 10_000, "reasons": []}
    )
    case = _case(db_session, source_alert_id=alert.id)
    r = verdict_reasoning.explain(db_session, case)
    ti = next(s for s in r["signals"] if s["signal"] == "threat_intel")
    assert ti["contribution"] <= 0.20


# ---------------------------------------------------------------------------
# Behaviour at realistic volume, not just on an empty database
# ---------------------------------------------------------------------------

def test_reasoning_holds_up_with_hundreds_of_alerts(db_session):
    """The empty-database path was well covered; this exercises the loaded one."""
    ip = "203.0.113.55"
    db_session.bulk_save_objects(
        [
            SecurityAlert(org_id=ORG, severity="HIGH", source="edr", message=f"evt {i}", source_ip=ip)
            for i in range(300)
        ]
    )
    db_session.bulk_save_objects(
        [
            Asset(org_id=ORG, name=f"host{i}", asset_type="host", criticality=(i % 5) + 1)
            for i in range(200)
        ]
    )
    db_session.commit()

    alert = _alert(db_session, source_ip=ip)
    case = _case(db_session, source_alert_id=alert.id)

    r = verdict_reasoning.explain(db_session, case)

    corr = next(s for s in r["signals"] if s["signal"] == "correlation")
    # The query is limited to 50 rows: the count must reflect what was actually
    # examined rather than implying a full scan of 300.
    assert corr["evidence"]["related_alerts"] <= 50
    assert corr["contribution"] <= 0.15, "a busy IP must not blow past the signal cap"
    assert 0.0 <= r["confidence"] <= 1.0


def test_explain_never_raises_even_on_a_broken_case(db_session):
    case = _case(db_session, source_alert_id=999999)  # dangling reference
    r = verdict_reasoning.explain(db_session, case)
    assert "confidence" in r
    assert isinstance(r["signals"], list)


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------

def test_reasoning_endpoint_returns_the_report(client, auth_headers, db_session):
    alert = _alert(db_session, source_ip="203.0.113.9")
    case = _case(db_session, source_alert_id=alert.id)

    r = client.get(f"/api/v1/analyst/cases/{case.id}/reasoning", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "signals" in body and "unavailable" in body
    assert "summary" in body


def test_reasoning_endpoint_404s_for_an_unknown_case(client, auth_headers):
    r = client.get("/api/v1/analyst/cases/424242/reasoning", headers=auth_headers)
    assert r.status_code == 404
