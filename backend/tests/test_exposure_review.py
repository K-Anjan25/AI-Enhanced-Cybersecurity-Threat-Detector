"""Exposures must be reviewable, because attack paths are computed from them.

`analyze_paths` treats every open exposure as an attacker's way in. A wrong
entry — a hostname that resolves nowhere, a service long decommissioned —
therefore keeps generating routes to crown jewels, and the operator had no way
to say so: the model carried `fixed` and `ignored` states that no code path
ever set.
"""

import pytest

from app.models.exposure import ASM_AssetExposure
from app.models.risk_based import Asset
from app.services import attack_path_service, exposure_service

ORG = 1


def _exposure(db, **kw):
    kw.setdefault("name", "web.acme.com")
    kw.setdefault("ip_address", "10.0.0.5")
    kw.setdefault("exposure_type", "open_port")
    kw.setdefault("severity", "HIGH")
    kw.setdefault("status", "open")
    kw.setdefault("port", 443)
    row = ASM_AssetExposure(org_id=ORG, **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# The review loop
# ---------------------------------------------------------------------------

def test_dismissing_an_exposure_retracts_its_attack_path(db_session):
    """The reason this page exists: bad input, retractable conclusion."""
    db_session.add(
        Asset(org_id=ORG, name="crown", asset_type="host", criticality=5, ip_address="10.0.0.5")
    )
    exposure = _exposure(db_session)

    assert len(attack_path_service.analyze_paths(db_session, ORG)) == 1

    exposure_service.set_exposure_status(
        db_session, ORG, exposure.id, "ignored", note="decommissioned last year"
    )

    assert attack_path_service.analyze_paths(db_session, ORG) == []


def test_marking_fixed_also_removes_it_from_open(db_session):
    exposure = _exposure(db_session)
    exposure_service.set_exposure_status(db_session, ORG, exposure.id, "fixed")

    still_open = exposure_service.list_exposures(db_session, ORG, status="open")
    assert exposure.id not in [e.id for e in still_open]


def test_the_reason_is_kept_with_the_evidence(db_session):
    """A later reader needs to know why this was dismissed, not just that it was."""
    exposure = _exposure(db_session, evidence_json={"source": "certificate_transparency"})

    exposure_service.set_exposure_status(
        db_session, ORG, exposure.id, "ignored", note="never resolved"
    )

    db_session.refresh(exposure)
    assert exposure.evidence_json["status_note"] == "never resolved"
    assert exposure.evidence_json["status_set_at"]
    # The original evidence must survive the annotation.
    assert exposure.evidence_json["source"] == "certificate_transparency"


def test_an_unknown_status_is_refused(db_session):
    exposure = _exposure(db_session)
    with pytest.raises(ValueError, match="Unknown status"):
        exposure_service.set_exposure_status(db_session, ORG, exposure.id, "maybe")

    db_session.refresh(exposure)
    assert exposure.status == "open"


def test_a_missing_exposure_is_not_found(db_session):
    with pytest.raises(ValueError, match="not found"):
        exposure_service.set_exposure_status(db_session, ORG, 424242, "fixed")


def test_another_tenants_exposure_cannot_be_touched(db_session):
    exposure = _exposure(db_session)
    with pytest.raises(ValueError, match="not found"):
        exposure_service.set_exposure_status(db_session, 999, exposure.id, "ignored")


# ---------------------------------------------------------------------------
# The summary
# ---------------------------------------------------------------------------

def test_summary_counts_only_open_exposures(db_session):
    first = _exposure(db_session, severity="CRITICAL")
    _exposure(db_session, name="two.acme.com", severity="HIGH")

    before = exposure_service.get_exposure_summary(db_session, ORG)
    assert before["open_exposures"] == 2
    assert before["critical"] == 1

    exposure_service.set_exposure_status(db_session, ORG, first.id, "fixed")

    after = exposure_service.get_exposure_summary(db_session, ORG)
    assert after["open_exposures"] == 1
    assert after["critical"] == 0
    assert after["total_exposures"] == 2, "history is kept, not deleted"


def test_summary_no_longer_reports_an_invented_risk_score(db_session):
    """`critical*20 + high*10` was a weighted count presented as a percentage."""
    _exposure(db_session, severity="CRITICAL")
    summary = exposure_service.get_exposure_summary(db_session, ORG)
    assert "risk_score" not in summary


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_status_endpoint_updates_the_exposure(client, admin_headers, db_session):
    exposure = _exposure(db_session)

    r = client.post(
        f"/api/v1/exposure/{exposure.id}/status",
        headers=admin_headers,
        json={"status": "ignored", "note": "not ours"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


def test_status_endpoint_rejects_a_bad_status(client, admin_headers, db_session):
    exposure = _exposure(db_session)

    r = client.post(
        f"/api/v1/exposure/{exposure.id}/status",
        headers=admin_headers,
        json={"status": "banana"},
    )
    assert r.status_code == 400
    assert "Unknown status" in r.json()["detail"]


def test_status_endpoint_404s_for_a_missing_exposure(client, admin_headers):
    r = client.post(
        "/api/v1/exposure/424242/status",
        headers=admin_headers,
        json={"status": "fixed"},
    )
    assert r.status_code == 404
