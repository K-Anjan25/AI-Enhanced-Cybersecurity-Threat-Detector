"""Attack path analysis — how an attacker reaches the assets that matter.

A real shortest-path search over a graph built from rows that exist:

  * **Nodes** — the internet, every open ASM exposure, and every asset.
  * **Edges** — internet→exposure (T1190 exploit public-facing application),
    exposure→its host asset, and asset→asset lateral movement inferred from
    observed entity links, shared subnet, or shared business unit.
  * **Cost** — how much effort a hop takes. Exploiting an exposed critical
    service is cheap; pivoting between unrelated segments is expensive.

We then run Dijkstra from the internet to each crown jewel and keep the
cheapest route. The *choke point* is the edge whose removal most increases the
cost of the path — that is the single fix worth doing, which is the whole point
of the feature for a company with no security team.

If there are no crown jewels or no exposures, there is no path, and we record
nothing. An attack path with an invented hop is worse than no attack path.
"""

from __future__ import annotations

import heapq
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.attack_path import AttackPath, AttackPathFinding
from app.models.risk_based import Asset
from app.models.exposure import ASM_AssetExposure
from app.models.entity import Entity, EntityLink

def _now():
    return datetime.now(timezone.utc)


INTERNET = ("internet", 0)

# Effort to exploit an exposure, by how exposed it is. Lower = easier.
_EXPOSURE_COST = {
    "CRITICAL": 1.0,
    "HIGH": 2.0,
    "MEDIUM": 4.0,
    "LOW": 6.0,
}

# Effort to move laterally, by how the two assets are related.
_LATERAL_COST = {
    "observed_link": 1.0,   # we have actually seen these two talk
    "same_subnet": 3.0,     # same /24 — routine reachability
    "same_unit": 5.0,       # same business unit — plausible, unproven
}


def _subnet(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    parts = ip.strip().split(".")
    if len(parts) != 4:
        return None
    return ".".join(parts[:3])


def _asset_identifiers(asset: Asset) -> set[str]:
    return {
        v.strip().lower()
        for v in (asset.hostname, asset.ip_address, asset.name)
        if v and v.strip()
    }


def _observed_pairs(db: Session, org_id: int, assets: List[Asset]) -> set[Tuple[int, int]]:
    """Asset pairs we have actually observed communicating, via entity links."""
    ident_to_asset: Dict[str, int] = {}
    for asset in assets:
        for ident in _asset_identifiers(asset):
            ident_to_asset[ident] = asset.id

    if not ident_to_asset:
        return set()

    entities = {
        e.id: (e.value or "").strip().lower()
        for e in db.query(Entity).filter(Entity.org_id == org_id).all()
    }
    pairs: set[Tuple[int, int]] = set()
    for link in db.query(EntityLink).filter(EntityLink.org_id == org_id).all():
        src = ident_to_asset.get(entities.get(link.source_entity_id, ""))
        dst = ident_to_asset.get(entities.get(link.target_entity_id, ""))
        if src and dst and src != dst:
            pairs.add((src, dst))
            pairs.add((dst, src))
    return pairs


def _build_graph(
    db: Session, org_id: int, assets: List[Asset], exposures: List[ASM_AssetExposure]
) -> Dict[Tuple[str, int], List[Tuple[Tuple[str, int], float, Dict[str, Any]]]]:
    """Adjacency list keyed by (kind, id) with (neighbour, cost, edge_meta)."""
    graph: Dict[Tuple[str, int], List[Tuple[Tuple[str, int], float, Dict[str, Any]]]] = {}

    def edge(a, b, cost, meta):
        graph.setdefault(a, []).append((b, cost, meta))

    by_identifier: Dict[str, Asset] = {}
    for asset in assets:
        for ident in _asset_identifiers(asset):
            by_identifier[ident] = asset

    # Internet → exposure → the asset hosting it.
    for exp in exposures:
        node = ("exposure", exp.id)
        cost = _EXPOSURE_COST.get((exp.severity or "MEDIUM").upper(), 4.0)
        label = f"{exp.name}:{exp.port}" if exp.port else exp.name
        edge(
            INTERNET,
            node,
            cost,
            {
                "technique_id": "T1190",
                "technique": "Exploit Public-Facing Application",
                "label": f"{label} ({exp.exposure_type})",
            },
        )

        host = None
        for candidate in (exp.name, exp.ip_address):
            if candidate and candidate.strip().lower() in by_identifier:
                host = by_identifier[candidate.strip().lower()]
                break
        if host is not None:
            edge(node, ("asset", host.id), 0.0, {"technique_id": "T1133", "technique": "External Remote Services"})

    # Lateral movement between assets.
    observed = _observed_pairs(db, org_id, assets)
    for a in assets:
        for b in assets:
            if a.id == b.id:
                continue
            if (a.id, b.id) in observed:
                relation, cost = "observed_link", _LATERAL_COST["observed_link"]
            elif _subnet(a.ip_address) and _subnet(a.ip_address) == _subnet(b.ip_address):
                relation, cost = "same_subnet", _LATERAL_COST["same_subnet"]
            elif a.business_unit and a.business_unit == b.business_unit:
                relation, cost = "same_unit", _LATERAL_COST["same_unit"]
            else:
                continue
            edge(
                ("asset", a.id),
                ("asset", b.id),
                cost,
                {"technique_id": "T1021", "technique": "Remote Services", "relation": relation},
            )

    return graph


def _dijkstra(graph, source, target):
    """Cheapest route from source to target as [(node, edge_meta_in)]."""
    dist = {source: 0.0}
    prev: Dict[Any, Tuple[Any, Dict[str, Any]]] = {}
    queue = [(0.0, source)]
    visited = set()

    while queue:
        cost, node = heapq.heappop(queue)
        if node in visited:
            continue
        visited.add(node)
        if node == target:
            break
        for neighbour, weight, meta in graph.get(node, []):
            if neighbour in visited:
                continue
            new_cost = cost + weight
            if new_cost < dist.get(neighbour, float("inf")):
                dist[neighbour] = new_cost
                prev[neighbour] = (node, meta)
                heapq.heappush(queue, (new_cost, neighbour))

    if target not in dist:
        return None, float("inf")

    route: List[Tuple[Any, Dict[str, Any]]] = []
    cursor = target
    while cursor != source:
        parent, meta = prev[cursor]
        route.append((cursor, meta))
        cursor = parent
    route.append((source, {}))
    route.reverse()
    return route, dist[target]


def analyze_paths(db: Session, org_id: int) -> List[AttackPath]:
    """Find the cheapest internet→crown-jewel route for each critical asset."""
    crown_jewels = (
        db.query(Asset).filter(Asset.org_id == org_id, Asset.criticality >= 5).all()
    )
    assets = db.query(Asset).filter(Asset.org_id == org_id).all()
    exposures = (
        db.query(ASM_AssetExposure)
        .filter(ASM_AssetExposure.org_id == org_id, ASM_AssetExposure.status == "open")
        .all()
    )

    # No crown jewels or no way in means there is genuinely no path to report.
    if not crown_jewels or not exposures:
        return []

    graph = _build_graph(db, org_id, assets, exposures)
    asset_by_id = {a.id: a for a in assets}
    exposure_by_id = {e.id: e for e in exposures}

    results: List[AttackPath] = []
    for jewel in crown_jewels:
        route, cost = _dijkstra(graph, INTERNET, ("asset", jewel.id))
        if route is None:
            continue

        nodes: List[Dict[str, Any]] = []
        for (kind, ident), meta in route:
            if kind == "internet":
                nodes.append({"type": "internet", "name": "Internet"})
            elif kind == "exposure":
                exp = exposure_by_id.get(ident)
                if exp is None:
                    continue
                nodes.append(
                    {
                        "type": "exposure",
                        "exposure_id": exp.id,
                        "name": meta.get("label") or exp.name,
                        "technique_id": meta.get("technique_id"),
                        "technique": meta.get("technique"),
                        "severity": exp.severity,
                    }
                )
            else:
                asset = asset_by_id.get(ident)
                if asset is None:
                    continue
                nodes.append(
                    {
                        "type": "asset",
                        "asset_id": asset.id,
                        "name": asset.name,
                        "criticality": asset.criticality,
                        "technique_id": meta.get("technique_id"),
                        "technique": meta.get("technique"),
                        "relation": meta.get("relation"),
                    }
                )

        if len(nodes) < 2:
            continue

        # Risk rises with the value of the target and falls with the effort
        # required. A cheap route to a criticality-5 asset is the worst case.
        risk_score = max(
            0.0, min(100.0, (jewel.criticality / 5.0) * 100.0 - (cost * 5.0))
        )

        existing = (
            db.query(AttackPath)
            .filter(AttackPath.org_id == org_id, AttackPath.crown_jewel_asset_id == jewel.id)
            .first()
        )
        if existing:
            existing.path_json = nodes
            existing.risk_score = risk_score
            existing.status = "active"
            db.commit()
            db.refresh(existing)
            path_row = existing
        else:
            path_row = AttackPath(
                org_id=org_id,
                name=f"Internet → {jewel.name}",
                description=(
                    f"{len(nodes) - 1} hop(s) from the internet to {jewel.name} "
                    f"(criticality {jewel.criticality}/5), attacker effort {cost:.1f}."
                ),
                path_json=nodes,
                risk_score=risk_score,
                path_type="internet_to_crown_jewel",
                crown_jewel_asset_id=jewel.id,
                status="active",
            )
            db.add(path_row)
            db.commit()
            db.refresh(path_row)

        _record_choke_point(db, org_id, path_row, nodes, graph, jewel)
        results.append(path_row)

    return results


def _record_choke_point(db, org_id, path_row, nodes, graph, jewel) -> None:
    """The single hop whose removal costs the attacker the most.

    Computed by re-running the search with each edge removed and keeping the
    one that raises the resulting cost furthest (unreachable = best fix).
    """
    db.query(AttackPathFinding).filter(
        AttackPathFinding.path_id == path_row.id, AttackPathFinding.status == "open"
    ).delete(synchronize_session=False)

    exposure_nodes = [n for n in nodes if n.get("type") == "exposure"]
    if not exposure_nodes:
        db.commit()
        return

    best = None
    for candidate in exposure_nodes:
        pruned = {
            node: [
                (nbr, cost, meta)
                for (nbr, cost, meta) in edges
                if nbr != ("exposure", candidate["exposure_id"])
            ]
            for node, edges in graph.items()
        }
        _, new_cost = _dijkstra(pruned, INTERNET, ("asset", jewel.id))
        if best is None or new_cost > best[1]:
            best = (candidate, new_cost)

    if best is None:
        db.commit()
        return

    candidate, new_cost = best
    unreachable = new_cost == float("inf")
    db.add(
        AttackPathFinding(
            org_id=org_id,
            path_id=path_row.id,
            title=f"Fix {candidate['name']} to break the route to {jewel.name}",
            choke_point_exposure_id=candidate.get("exposure_id"),
            choke_point_asset_id=jewel.id,
            severity="CRITICAL" if unreachable else "HIGH",
            remediation=(
                f"Closing {candidate['name']} removes every known route to {jewel.name}."
                if unreachable
                else f"Closing {candidate['name']} raises attacker effort to {new_cost:.1f}."
            ),
        )
    )
    db.commit()


def list_paths(db: Session, org_id: int) -> List[AttackPath]:
    return (
        db.query(AttackPath)
        .filter(AttackPath.org_id == org_id, AttackPath.status == "active")
        .order_by(AttackPath.risk_score.desc())
        .all()
    )


def list_findings(db: Session, org_id: int) -> List[AttackPathFinding]:
    return (
        db.query(AttackPathFinding)
        .filter(AttackPathFinding.org_id == org_id, AttackPathFinding.status == "open")
        .all()
    )


def serialize_path(p: AttackPath) -> Dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "path": p.path_json,
        "risk_score": p.risk_score,
        "path_type": p.path_type,
        "crown_jewel_asset_id": p.crown_jewel_asset_id,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def serialize_finding(f: AttackPathFinding) -> Dict[str, Any]:
    return {
        "id": f.id,
        "path_id": f.path_id,
        "title": f.title,
        "choke_point_exposure_id": f.choke_point_exposure_id,
        "severity": f.severity,
        "remediation": f.remediation,
        "status": f.status,
    }
