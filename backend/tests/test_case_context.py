"""Case context integration: the risk modules must reach the analyst loop.

These tests exist to stop the regression this codebase already suffered once —
capability modules that store data nobody ever reads. Each test asserts that a
row written by a risk module actually changes what the analyst is told.
"""

from datetime import datetime, timezone

import pytest

from app.models import Case, Entity, SecurityAlert
from app.models.attack_path import AttackPath
from app.models.drp import DRP_Monitor, DRP_Finding
from app.models.posture_score import PostureScore
from app.models.risk_based import Asset
from app.services import case_context


ORG = 1


def _make_case(db, *, entity_values=("victim@acme.com", "fileserver01")):
    """A pending analyst case whose blast radius names real entities."""
    alert = SecurityAlert(
        org_id=ORG,
        alert_type="credential_leak",
        severity="CRITICAL",
        score=90,
        message="credential reuse",
    )
    db.add(alert)
    db.flush()

    nodes = []
    for value in entity_values:
        entity = Entity(org_id=ORG, entity_type="email" if "@" in value else "host", value=value)
        db.add(entity)
        db.flush()
        nodes.append({"id": entity.id, "entity_type": entity.entity_type, "value": entity.value})

    case = Case(
        org_id=ORG,
        title="Leaked credential in use",
        status="open",
        priority="critical",
        kind="analyst",
        source_alert_id=alert.id,
        blast_radius={"root_entity_id": nodes[0]["id"], "nodes": nodes, "links": []},
        decision="pending",
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def test_context_is_empty_when_no_modules_have_data(db_session):
    """No invented context. Absent data must produce absent keys."""
    case = _make_case(db_session)
    context = case_context.build(db_session, case)
    assert context == {}
    assert case_context.summarize(context) == []


def test_crown_jewel_reach_counts_hops_from_the_case(db_session):
    case = _make_case(db_session)

    jewel = Asset(org_id=ORG, name="dc01", asset_type="host", criticality=5)
    db_session.add(jewel)
    db_session.flush()

    # fileserver01 (in the case) -> dc01 (crown jewel) is two hops from the net.
    db_session.add(
        AttackPath(
            org_id=ORG,
            name="Internet -> dc01",
            path_json=[
                {"type": "internet", "name": "Internet"},
                {"type": "asset", "name": "fileserver01", "technique_id": "T1190"},
                {"type": "asset", "name": "dc01", "asset_id": jewel.id, "technique_id": "T1021"},
            ],
            risk_score=88.0,
            crown_jewel_asset_id=jewel.id,
            status="active",
        )
    )
    db_session.commit()

    context = case_context.build(db_session, case)
    reach = context["crown_jewel_reach"]

    assert reach["hops"] == 1, "entry at fileserver01 leaves one hop to the jewel"
    assert reach["crown_jewel"] == "dc01"
    assert "T1021" in reach["techniques"]

    summary = " ".join(case_context.summarize(context))
    assert "1 hop from dc01" in summary


def test_posture_reports_points_at_risk_for_this_case(db_session):
    case = _make_case(db_session)
    db_session.add(PostureScore(org_id=ORG, overall_score=72.0, trend="stable"))
    db_session.commit()

    context = case_context.build(db_session, case)
    posture = context["posture"]

    assert posture["current_score"] == 72.0
    # A critical case puts 8 points at risk.
    assert posture["points_at_risk"] == 8.0
    assert posture["projected_score"] == 64.0

    summary = " ".join(case_context.summarize(context))
    assert "drops 8.0 points to 64.0" in summary


def test_leaked_credential_is_matched_to_the_case_identity(db_session):
    case = _make_case(db_session)

    monitor = DRP_Monitor(org_id=ORG, name="Domain", monitor_type="domain", keyword="acme.com")
    db_session.add(monitor)
    db_session.flush()
    db_session.add(
        DRP_Finding(
            org_id=ORG,
            monitor_id=monitor.id,
            finding_type="leaked_credential",
            severity="CRITICAL",
            title="Credential exposed",
            description="victim@acme.com found in a public dump",
            evidence_json={"paste": "https://example.invalid/x"},
            source="paste_site",
            status="open",
        )
    )
    db_session.commit()

    context = case_context.build(db_session, case)
    leaked = context["leaked_credentials"]

    assert len(leaked) == 1
    assert leaked[0]["identity"] == "victim@acme.com"

    summary = " ".join(case_context.summarize(context))
    assert "already exposed publicly" in summary


def test_unrelated_drp_finding_is_not_attached(db_session):
    """Context must be about *this* case, not everything in the tenant."""
    case = _make_case(db_session)

    monitor = DRP_Monitor(org_id=ORG, name="Domain", monitor_type="domain", keyword="acme.com")
    db_session.add(monitor)
    db_session.flush()
    db_session.add(
        DRP_Finding(
            org_id=ORG,
            monitor_id=monitor.id,
            finding_type="leaked_credential",
            severity="HIGH",
            title="Credential exposed",
            description="someone-else@acme.com found in a dump",
            evidence_json={},
            source="paste_site",
            status="open",
        )
    )
    db_session.commit()

    context = case_context.build(db_session, case)
    assert "leaked_credentials" not in context


def test_build_never_raises_on_malformed_blast_radius(db_session):
    """Enrichment failure must not be able to break the analyst loop."""
    case = _make_case(db_session)
    case.blast_radius = {"nodes": "not-a-list"}
    db_session.commit()

    assert case_context.build(db_session, case) == {}
