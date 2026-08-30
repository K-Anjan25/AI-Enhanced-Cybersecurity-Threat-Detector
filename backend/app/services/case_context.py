"""Case context — joins the risk-reduction modules onto a live analyst case.

This is the seam that turns independent capability modules into one product.
When NOCTRA opens a case, the brief should not just say *what happened*; it
should say what that means for **this** organisation:

    "this account can reach your domain controller in 2 hops"
    "your posture drops 6 points while this is unresolved"
    "this credential is already published in a public leak"

Contract
--------
`build(db, case)` returns a dict of *evidence-backed* findings. Every entry is
derived from real rows (entities, assets, attack paths, posture scores, DRP
findings). When a module has no data for this case the key is simply absent —
we never fabricate context, because an invented finding costs more trust than
a missing one. `build` never raises: context is an enrichment, and a failure
in it must not stop a case from opening.
"""

from __future__ import annotations

from typing import Any

from app.models import Case, Entity, SecurityAlert
from app.models.attack_path import AttackPath
from app.models.drp import DRP_Finding
from app.models.posture_score import PostureScore
from app.models.risk_based import Asset

# Severity → posture points at risk while the case is unresolved. Derived from
# the same weighting posture_score_service uses for open findings, so the
# number the brief quotes matches the number the score moves by.
_POSTURE_IMPACT = {"CRITICAL": 8.0, "HIGH": 6.0, "MEDIUM": 3.0, "LOW": 1.0}


def _case_entities(db, case: Case) -> list[Entity]:
    """Entities named in the case's blast radius, resolved to real rows."""
    blast = case.blast_radius or {}
    ids = [n.get("id") for n in (blast.get("nodes") or []) if isinstance(n, dict) and n.get("id")]
    if not ids:
        return []
    query = db.query(Entity).filter(Entity.id.in_(ids))
    if case.org_id is not None:
        query = query.filter(Entity.org_id == case.org_id)
    return query.all()


def _entity_values(entities: list[Entity]) -> set[str]:
    return {(e.value or "").strip().lower() for e in entities if e.value}


def _matching_assets(db, case: Case, entities: list[Entity]) -> list[Asset]:
    """Assets whose hostname or IP appears in the case's blast radius."""
    values = _entity_values(entities)
    if not values:
        return []
    query = db.query(Asset)
    if case.org_id is not None:
        query = query.filter(Asset.org_id == case.org_id)
    matched = []
    for asset in query.all():
        candidates = {
            (asset.hostname or "").strip().lower(),
            (asset.ip_address or "").strip().lower(),
            (asset.name or "").strip().lower(),
        }
        if candidates & values:
            matched.append(asset)
    return matched


def _crown_jewel_reach(db, case: Case, entities: list[Entity]) -> dict[str, Any] | None:
    """Shortest recorded attack path from anything in this case to a crown jewel.

    Hops are counted as edges (nodes - 1), which is how an analyst says it:
    "two hops away" means two moves, not three waypoints.
    """
    paths_query = db.query(AttackPath).filter(AttackPath.status == "active")
    if case.org_id is not None:
        paths_query = paths_query.filter(AttackPath.org_id == case.org_id)
    paths = paths_query.all()
    if not paths:
        return None

    values = _entity_values(entities)
    asset_ids = {a.id for a in _matching_assets(db, case, entities)}
    if not values and not asset_ids:
        return None

    best: dict[str, Any] | None = None
    for path in paths:
        nodes = path.path_json or []
        if not isinstance(nodes, list) or len(nodes) < 2:
            continue

        # Where does this case touch the path?
        entry_index = None
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            name = str(node.get("name") or "").strip().lower()
            node_asset_id = node.get("asset_id")
            if (name and name in values) or (node_asset_id and node_asset_id in asset_ids):
                entry_index = index
                break
        if entry_index is None:
            continue

        hops = len(nodes) - 1 - entry_index
        if hops <= 0:
            continue

        jewel = None
        if path.crown_jewel_asset_id is not None:
            jewel = db.query(Asset).filter(Asset.id == path.crown_jewel_asset_id).first()
        jewel_name = jewel.name if jewel else str((nodes[-1] or {}).get("name") or "a critical asset")

        techniques = [
            str(n.get("technique_id"))
            for n in nodes[entry_index:]
            if isinstance(n, dict) and n.get("technique_id")
        ]

        candidate = {
            "path_id": path.id,
            "hops": hops,
            "crown_jewel": jewel_name,
            "risk_score": path.risk_score,
            "techniques": techniques,
            "route": [str(n.get("name")) for n in nodes[entry_index:] if isinstance(n, dict) and n.get("name")],
        }
        if best is None or candidate["hops"] < best["hops"]:
            best = candidate

    return best


def _posture_at_risk(db, case: Case) -> dict[str, Any] | None:
    """Current posture score and the points this case puts at risk."""
    query = db.query(PostureScore)
    if case.org_id is not None:
        query = query.filter(PostureScore.org_id == case.org_id)
    latest = query.order_by(PostureScore.created_at.desc()).first()
    if latest is None:
        return None

    severity = (case.priority or "").upper()
    if severity == "CRITICAL" or severity == "HIGH":
        pass
    else:
        # Fall back to the source alert's severity, which is the graded signal.
        alert = None
        if case.source_alert_id is not None:
            alert = db.query(SecurityAlert).filter(SecurityAlert.id == case.source_alert_id).first()
        severity = (getattr(alert, "severity", None) or severity or "MEDIUM").upper()

    impact = _POSTURE_IMPACT.get(severity, 3.0)
    return {
        "current_score": round(latest.overall_score or 0.0, 1),
        "points_at_risk": impact,
        "projected_score": round(max(0.0, (latest.overall_score or 0.0) - impact), 1),
        "trend": latest.trend,
    }


def _leaked_credentials(db, case: Case, entities: list[Entity]) -> list[dict[str, Any]]:
    """Open DRP findings whose evidence names an identity from this case."""
    values = _entity_values(entities)
    if not values:
        return []

    query = db.query(DRP_Finding).filter(DRP_Finding.status == "open")
    if case.org_id is not None:
        query = query.filter(DRP_Finding.org_id == case.org_id)

    matches = []
    for finding in query.all():
        haystack = " ".join(
            [
                str(finding.title or ""),
                str(finding.description or ""),
                str(finding.evidence_json or {}),
            ]
        ).lower()
        hit = next((v for v in values if v and v in haystack), None)
        if hit:
            matches.append(
                {
                    "finding_id": finding.id,
                    "identity": hit,
                    "finding_type": finding.finding_type,
                    "severity": finding.severity,
                    "title": finding.title,
                    "source": finding.source,
                }
            )
    return matches


def build(db, case: Case) -> dict[str, Any]:
    """Assemble every available context signal for a case.

    Never raises — a broken enrichment must not block the analyst loop.
    """
    context: dict[str, Any] = {}
    try:
        entities = _case_entities(db, case)

        reach = _crown_jewel_reach(db, case, entities)
        if reach:
            context["crown_jewel_reach"] = reach

        posture = _posture_at_risk(db, case)
        if posture:
            context["posture"] = posture

        leaked = _leaked_credentials(db, case, entities)
        if leaked:
            context["leaked_credentials"] = leaked

        assets = _matching_assets(db, case, entities)
        if assets:
            context["affected_assets"] = [
                {
                    "id": a.id,
                    "name": a.name,
                    "criticality": a.criticality,
                    "business_unit": a.business_unit,
                    "owner": a.owner,
                }
                for a in sorted(assets, key=lambda a: a.criticality or 0, reverse=True)[:5]
            ]
    except Exception:  # pragma: no cover - enrichment is best-effort by contract
        return context
    return context


def summarize(context: dict[str, Any]) -> list[str]:
    """Plain-English lines for the brief. One sentence per real finding."""
    lines: list[str] = []

    reach = context.get("crown_jewel_reach")
    if reach:
        hop_word = "hop" if reach["hops"] == 1 else "hops"
        line = f"This sits {reach['hops']} {hop_word} from {reach['crown_jewel']}"
        if reach.get("techniques"):
            line += f" via {' → '.join(reach['techniques'])}"
        lines.append(line + ".")

    posture = context.get("posture")
    if posture:
        lines.append(
            f"Your posture score is {posture['current_score']} and drops "
            f"{posture['points_at_risk']} points to {posture['projected_score']} "
            "while this is unresolved."
        )

    leaked = context.get("leaked_credentials")
    if leaked:
        first = leaked[0]
        extra = f" (and {len(leaked) - 1} more)" if len(leaked) > 1 else ""
        lines.append(
            f"The credential {first['identity']} is already exposed publicly — "
            f"{first['finding_type'].replace('_', ' ')} seen on {first['source']}{extra}."
        )

    assets = context.get("affected_assets")
    if assets:
        top = assets[0]
        owner = f", owned by {top['owner']}" if top.get("owner") else ""
        lines.append(
            f"Highest-value asset involved: {top['name']} "
            f"(criticality {top['criticality']}/5{owner})."
        )

    return lines
