"""The risk modules must derive from real rows, never fabricate findings.

Each test pins one of the honesty properties that make these numbers safe to
show a customer: no invented findings, no hardcoded sub-scores, and an explicit
statement of what could not be checked.
"""

import pytest

from app.models import Case, Entity, EntityLink, SecurityAlert
from app.models.attack_path import AttackPath, AttackPathFinding
from app.models.drp import DRP_Monitor, DRP_Finding
from app.models.exposure import ASM_AssetExposure
from app.models.org import Org
from app.models.posture_score import PostureScore
from app.models.risk_based import Asset
from app.models.user import User
from app.services import attack_path_service, drp_service, posture_score_service


ORG = 1


# ---------------------------------------------------------------------------
# DRP
# ---------------------------------------------------------------------------

def test_typosquat_candidates_are_real_variations():
    candidates = drp_service.typosquat_candidates("acme.com")
    domains = {c["domain"] for c in candidates}

    assert "acme.com" not in domains, "the source domain is not its own lookalike"
    assert "cme.com" in domains, "character omission"
    assert "acme-login.com" in domains, "credential-phishing keyword suffix"
    assert all(c["technique"] for c in candidates), "every candidate explains itself"


def test_typosquat_includes_the_rn_m_confusable():
    """'rn' for 'm' is the highest-yield lookalike in the wild."""
    domains = [c["domain"] for c in drp_service.typosquat_candidates("acme.com")]
    assert "acrne.com" in domains
    assert domains.index("acrne.com") < 3, "must survive the result limit"


def test_every_candidate_is_actually_registrable():
    """An unregistrable candidate is a wasted CT lookup, not a finding."""
    for source in ("acme.com", "microsoft.com", "my-shop.co.uk"):
        for c in drp_service.typosquat_candidates(source, limit=200):
            assert drp_service._is_registrable(c["domain"]), c["domain"]
            assert "@" not in c["domain"], "@ is a font trick, not a domain"


def test_typosquat_handles_degenerate_input():
    assert drp_service.typosquat_candidates("") == []
    assert drp_service.typosquat_candidates("localhost") != []


def test_seed_monitors_uses_real_org_identity_not_example_com(db_session):
    db_session.add(Org(id=ORG, name="Acme Ltd", slug="acme"))
    db_session.add(
        User(
            org_id=ORG,
            username="owner",
            email="owner@acme.com",
            password="x",
            role="ANALYST",
        )
    )
    db_session.commit()

    monitors = drp_service.seed_monitors(db_session, ORG)
    keywords = {m.keyword for m in monitors}

    assert "acme.com" in keywords, "monitors the domain the org actually uses"
    assert "Acme Ltd" in keywords
    assert not any("example.com" in k for k in keywords), "no placeholder domains"


def test_seed_monitors_creates_nothing_without_identity(db_session):
    """No org name, no users — creating placeholders would be noise."""
    assert drp_service.seed_monitors(db_session, 999) == []


def test_scan_never_fabricates_leaked_credentials(db_session):
    """Without a breach-database key, DRP must report nothing, not invent."""
    db_session.add(Org(id=ORG, name="Acme Ltd", slug="acme"))
    db_session.add(
        User(org_id=ORG, username="o", email="o@acme.com", password="x", role="ANALYST")
    )
    db_session.commit()
    drp_service.seed_monitors(db_session, ORG)

    report = drp_service.scan_report(db_session, ORG)
    types = {f["finding_type"] for f in report["findings"]}

    assert "leaked_credential" not in types, "no key configured, so no credential claims"
    assert report["providers"]["dark_web"]["enabled"] is False
    assert "Not checked" in report["coverage_note"], "the gap is stated, not hidden"


def test_typosquat_finding_admits_registration_is_unverified(db_session):
    db_session.add(Org(id=ORG, name="Acme Ltd", slug="acme"))
    db_session.add(
        User(org_id=ORG, username="o", email="o@acme.com", password="x", role="ANALYST")
    )
    db_session.commit()
    drp_service.seed_monitors(db_session, ORG)

    findings = drp_service.scan_drp(db_session, ORG)
    squat = next(f for f in findings if f.finding_type == "typosquat_candidate")

    assert squat.evidence_json["registration_checked"] is False
    assert "NOT checked" in squat.description


def test_scan_is_idempotent(db_session):
    db_session.add(Org(id=ORG, name="Acme Ltd", slug="acme"))
    db_session.add(
        User(org_id=ORG, username="o", email="o@acme.com", password="x", role="ANALYST")
    )
    db_session.commit()
    drp_service.seed_monitors(db_session, ORG)

    drp_service.scan_drp(db_session, ORG)
    first = len(drp_service.list_findings(db_session, ORG))
    drp_service.scan_drp(db_session, ORG)
    second = len(drp_service.list_findings(db_session, ORG))

    assert first == second, "re-scanning must not duplicate open findings"


# ---------------------------------------------------------------------------
# Attack paths
# ---------------------------------------------------------------------------

def _exposed_host(db, name="web01", ip="10.0.0.10", severity="CRITICAL"):
    db.add(
        ASM_AssetExposure(
            org_id=ORG,
            asset_type="host",
            name=name,
            ip_address=ip,
            port=443,
            service="https",
            exposure_type="exposed_service",
            severity=severity,
            status="open",
        )
    )


def test_no_crown_jewels_means_no_paths(db_session):
    _exposed_host(db_session)
    db_session.commit()
    assert attack_path_service.analyze_paths(db_session, ORG) == []


def test_no_exposures_means_no_paths(db_session):
    db_session.add(Asset(org_id=ORG, name="dc01", criticality=5))
    db_session.commit()
    assert attack_path_service.analyze_paths(db_session, ORG) == []


def test_path_traverses_real_lateral_edges(db_session):
    """web01 is exposed; dc01 shares its subnet, so the route is reachable."""
    db_session.add(Asset(org_id=ORG, name="web01", hostname="web01", ip_address="10.0.0.10", criticality=3))
    db_session.add(Asset(org_id=ORG, name="dc01", hostname="dc01", ip_address="10.0.0.5", criticality=5))
    _exposed_host(db_session, name="web01", ip="10.0.0.10")
    db_session.commit()

    paths = attack_path_service.analyze_paths(db_session, ORG)
    assert len(paths) == 1

    names = [n["name"] for n in paths[0].path_json]
    assert names[0] == "Internet"
    assert names[-1] == "dc01"
    assert any("web01" in n for n in names), "route goes through the exposed host"


def test_unreachable_crown_jewel_yields_no_path(db_session):
    """A jewel on an unrelated segment with no observed link is not reachable."""
    db_session.add(Asset(org_id=ORG, name="web01", hostname="web01", ip_address="10.0.0.10", criticality=3))
    db_session.add(
        Asset(org_id=ORG, name="vault", hostname="vault", ip_address="192.168.99.9", criticality=5)
    )
    _exposed_host(db_session, name="web01", ip="10.0.0.10")
    db_session.commit()

    assert attack_path_service.analyze_paths(db_session, ORG) == []


def test_choke_point_identifies_the_fix(db_session):
    db_session.add(Asset(org_id=ORG, name="web01", hostname="web01", ip_address="10.0.0.10", criticality=3))
    db_session.add(Asset(org_id=ORG, name="dc01", hostname="dc01", ip_address="10.0.0.5", criticality=5))
    _exposed_host(db_session, name="web01", ip="10.0.0.10")
    db_session.commit()

    attack_path_service.analyze_paths(db_session, ORG)
    findings = attack_path_service.list_findings(db_session, ORG)

    assert findings, "a path must name the single fix that breaks it"
    assert "web01" in findings[0].title
    # Removing the only entry point makes the jewel unreachable.
    assert findings[0].severity == "CRITICAL"


def test_easier_exposure_scores_higher_risk(db_session):
    """A critical-severity way in is cheaper, so the path is more dangerous."""
    db_session.add(Asset(org_id=ORG, name="web01", hostname="web01", ip_address="10.0.0.10", criticality=5))
    _exposed_host(db_session, name="web01", ip="10.0.0.10", severity="CRITICAL")
    db_session.commit()
    high = attack_path_service.analyze_paths(db_session, ORG)[0].risk_score

    db_session.query(AttackPathFinding).delete()
    db_session.query(AttackPath).delete()
    db_session.query(ASM_AssetExposure).delete()
    _exposed_host(db_session, name="web01", ip="10.0.0.10", severity="LOW")
    db_session.commit()
    low = attack_path_service.analyze_paths(db_session, ORG)[0].risk_score

    assert high > low


# ---------------------------------------------------------------------------
# Posture
# ---------------------------------------------------------------------------

def test_posture_omits_dimensions_it_cannot_measure(db_session):
    """An empty tenant must not be handed flattering constants."""
    score = posture_score_service.calculate_posture(db_session, ORG)

    assert "recover" in score.breakdown_json, "missing retention policy is a real gap"
    assert score.breakdown_json["recover"] == 20.0
    for absent in ("detect", "protect", "respond", "governance"):
        assert absent not in score.breakdown_json
    assert set(score.business_context_json["unmeasured_dimensions"]) == {
        "detect",
        "protect",
        "respond",
        "governance",
    }


def test_posture_never_hardcodes_governance_at_75(db_session):
    """The old implementation asserted recover=80 / governance=75 regardless."""
    score = posture_score_service.calculate_posture(db_session, ORG)
    assert score.breakdown_json.get("governance") != 75
    assert score.breakdown_json.get("recover") != 80


def test_respond_score_reflects_real_case_closure(db_session):
    for _ in range(3):
        db_session.add(Case(org_id=ORG, title="closed", status="closed"))
    db_session.add(Case(org_id=ORG, title="open", status="open"))
    db_session.commit()

    score = posture_score_service.calculate_posture(db_session, ORG)
    # 75% closure, minus 2 points for the single open case.
    assert score.breakdown_json["respond"] == pytest.approx(73.0)


def test_posture_produces_findings_only_for_weak_dimensions(db_session):
    for _ in range(9):
        db_session.add(Case(org_id=ORG, title="closed", status="closed"))
    db_session.add(Case(org_id=ORG, title="open", status="open"))
    db_session.commit()

    posture_score_service.calculate_posture(db_session, ORG)
    categories = {f.category for f in posture_score_service.list_findings(db_session, ORG)}

    assert "respond" not in categories, "88% closure is healthy, so no finding"
    assert "recover" in categories, "no retention policy is a genuine gap"


def test_recalculating_does_not_accumulate_stale_findings(db_session):
    posture_score_service.calculate_posture(db_session, ORG)
    first = len(posture_score_service.list_findings(db_session, ORG))
    posture_score_service.calculate_posture(db_session, ORG)
    second = len(posture_score_service.list_findings(db_session, ORG))

    assert first == second, "each reading replaces the previous findings"


# ---------------------------------------------------------------------------
# DRP + Certificate Transparency
# ---------------------------------------------------------------------------

def _org_with_domain(db):
    db.add(Org(id=ORG, name="Acme Ltd", slug="acme"))
    db.add(User(org_id=ORG, username="o", email="o@acme.com", password="x", role="ANALYST"))
    db.commit()
    drp_service.seed_monitors(db, ORG)


def _stub_ct(monkeypatch, registered=(), fail_reason=None):
    """Stand in for crt.sh: `registered` domains come back with a certificate."""
    from app.services import ct_log_client

    monkeypatch.setattr(ct_log_client, "is_enabled", lambda: True)

    def fake_lookup_many(domains, limit=12):
        out = []
        for d in domains[:limit]:
            if fail_reason:
                out.append(ct_log_client.CTResult(domain=d, ok=False, reason=fail_reason))
                break
            if d in registered:
                out.append(
                    ct_log_client.CTResult(
                        domain=d,
                        ok=True,
                        registered=True,
                        certificates=[{
                            "id": 1,
                            "issuer": "Let's Encrypt",
                            "not_before": "2026-02-01T00:00:00",
                            "not_after": "2026-05-01T00:00:00",
                            "names": [d],
                        }],
                    )
                )
            else:
                out.append(ct_log_client.CTResult(domain=d, ok=True, registered=False))
        return out

    monkeypatch.setattr(ct_log_client, "lookup_many", fake_lookup_many)


def test_ct_confirmed_lookalike_becomes_a_high_severity_finding(db_session, monkeypatch):
    _org_with_domain(db_session)
    _stub_ct(monkeypatch, registered={"acme-login.com"})

    findings = drp_service.scan_drp(db_session, ORG)
    confirmed = [f for f in findings if f.finding_type == "lookalike_domain_registered"]

    assert len(confirmed) == 1, "a real certificate is a real finding"
    f = confirmed[0]
    assert f.severity == "HIGH", "an existing lookalike outranks a hypothetical one"
    assert "acme-login.com" in f.title
    assert f.source == "certificate_transparency"
    assert f.evidence_json["registration_checked"] is True
    assert f.evidence_json["first_seen"] == "2026-02-01T00:00:00"
    assert f.evidence_json["issuers"] == ["Let's Encrypt"]
    assert f.evidence_json["technique"], "explains which typo pattern produced it"
    assert "crt.sh" in f.evidence_json["crtsh_url"]


def test_clean_ct_sweep_downgrades_the_candidate_list(db_session, monkeypatch):
    _org_with_domain(db_session)
    _stub_ct(monkeypatch, registered=set())

    drp_service.scan_drp(db_session, ORG)
    candidate = next(
        f for f in drp_service.list_findings(db_session, ORG)
        if f.finding_type == "typosquat_candidate"
    )

    assert candidate.severity == "LOW", "verified-clean is less urgent than unverified"
    assert candidate.evidence_json["registration_checked"] is True
    assert candidate.evidence_json["registered_confirmed"] == []
    assert "only covers publicly-trusted" in candidate.description, "states CT's blind spot"


def test_failed_ct_lookup_never_reads_as_clean(db_session, monkeypatch):
    """The trust-critical case: could-not-check must not look like nothing-found."""
    _org_with_domain(db_session)
    _stub_ct(monkeypatch, fail_reason="crt.sh rate limited this client (HTTP 429)")

    drp_service.scan_drp(db_session, ORG)
    candidate = next(
        f for f in drp_service.list_findings(db_session, ORG)
        if f.finding_type == "typosquat_candidate"
    )

    assert candidate.evidence_json["registration_checked"] is False
    assert "rate limited" in candidate.evidence_json["verification_error"]
    assert "not a clean result" in candidate.description
    assert candidate.source == "local_analysis", "do not credit CT for a failed run"


def test_coverage_note_credits_ct_when_it_ran(db_session, monkeypatch):
    _org_with_domain(db_session)
    _stub_ct(monkeypatch, registered=set())

    report = drp_service.scan_report(db_session, ORG)
    assert report["providers"]["certificate_transparency"]["enabled"] is True
    assert "certificate_transparency" in report["coverage_note"]
    assert "dark_web" in report["coverage_note"], "still names what was skipped"
