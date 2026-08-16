"""Entity / attack-graph service + endpoint tests."""

import pytest

from app.models import Entity, EntityLink, SecurityAlert, Org
from app.services import entity_graph


@pytest.fixture
def org_fixture(db_session):
    org = Org(name="GraphCo", slug="graphco")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def build_alert(db_session):
    def _make(message="Malicious payload deadbeefdeadbeefdeadbeefdeadbeefdeadbeef from 203.0.113.5", org_id=None):
        alert = SecurityAlert(
            alert_type="system_log",
            source_ip="203.0.113.5",
            severity="HIGH",
            score=0.87,
            message=message,
            org_id=org_id,
        )
        db_session.add(alert)
        db_session.flush()
        return alert
    return _make


def test_extract_entities_ip_and_hash():
    ents = entity_graph.extract_entities(
        "Suspicious hash aabbccddeeff0011223344556677889900112233 from 198.51.100.9",
        "198.51.100.9",
    )
    types = {e["entity_type"]: e["value"] for e in ents}
    assert types.get("hash") == "aabbccddeeff0011223344556677889900112233"
    assert types.get("ip") == "198.51.100.9"


def test_extract_entities_domain_and_email():
    ents = entity_graph.extract_entities("m.evil.org sent phishing to bob@corp.com", None)
    values = {(e["entity_type"], e["value"]) for e in ents}
    assert ("domain", "m.evil.org") in values
    assert ("email", "bob@corp.com") in values


def test_extract_entities_file():
    ents = entity_graph.extract_entities("download payload.exe delivered", None)
    assert any(e["entity_type"] == "file" and e["value"].endswith("payload.exe") for e in ents)


def test_upsert_entity_increments_occurrences(db_session, org_fixture):
    e1 = entity_graph.upsert_entity(db_session, "ip", "198.51.100.9", org_fixture.id)
    e2 = entity_graph.upsert_entity(db_session, "ip", "198.51.100.9", org_fixture.id)
    assert e1.id == e2.id
    assert e2.occurrences == 2


def test_upsert_entity_scoped_by_org(db_session, org_fixture):
    other = Org(name="Other", slug="other2")
    db_session.add(other)
    db_session.commit()

    entity_graph.upsert_entity(db_session, "ip", "203.0.113.1", org_fixture.id)
    entity_graph.upsert_entity(db_session, "ip", "203.0.113.1", other.id)
    total = db_session.query(Entity).filter(Entity.value == "203.0.113.1").count()
    assert total == 2


def test_index_alert_builds_links(db_session, org_fixture, build_alert):
    alert = build_alert(org_id=org_fixture.id)
    entity_graph.index_alert(db_session, alert)
    db_session.commit()

    ips = db_session.query(Entity).filter(Entity.entity_type == "ip").all()
    hashes = db_session.query(Entity).filter(Entity.entity_type == "hash").all()
    assert len(ips) == 1
    assert len(hashes) == 1
    links = db_session.query(EntityLink).all()
    assert len(links) >= 1
    assert links[0].org_id == org_fixture.id


def test_entity_graph_adjacency(db_session, org_fixture, build_alert):
    alert = build_alert(org_id=org_fixture.id)
    entity_graph.index_alert(db_session, alert)
    db_session.commit()

    root = db_session.query(Entity).filter(Entity.entity_type == "ip").first()
    payload = entity_graph.entity_graph(db_session, root.id, depth=1, org_id=org_fixture.id)
    assert payload["root"] == root.id
    assert any(n["entity_type"] == "hash" for n in payload["nodes"])
    assert any(l["source"] == root.id for l in payload["links"])


def test_serialize_entity_shape(db_session, org_fixture):
    entity = entity_graph.upsert_entity(db_session, "ip", "203.0.113.42", org_fixture.id)
    data = entity_graph.serialize_entity(entity)
    assert data["entity_type"] == "ip"
    assert data["occurrences"] == 1
    assert data["risk_score"] == 0.0


def test_graph_summary_counts_and_hubs(db_session, org_fixture, build_alert):
    alert = build_alert(org_id=org_fixture.id)
    entity_graph.index_alert(db_session, alert)
    db_session.commit()

    summary = entity_graph.graph_summary(db_session, org_id=org_fixture.id)
    assert summary["nodes"] >= 2
    assert summary["edges"] >= 1
    assert "ip" in summary["by_type"]
    assert summary["top_risk"][0]["value"] == "203.0.113.5"
    assert len(summary["hubs"]) >= 1
    assert "degree" in summary["hubs"][0]


def test_graph_summary_scoped_by_org(db_session, org_fixture, build_alert):
    other = Org(name="Other", slug="other3")
    db_session.add(other)
    db_session.commit()

    entity_graph.index_alert(db_session, build_alert(org_id=org_fixture.id))
    entity_graph.index_alert(db_session, build_alert(org_id=other.id, message="other deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"))
    db_session.commit()

    summary_a = entity_graph.graph_summary(db_session, org_id=org_fixture.id)
    summary_b = entity_graph.graph_summary(db_session, org_id=other.id)
    assert summary_a["nodes"] == 2
    assert summary_b["nodes"] == 2
    assert summary_a["by_type"]["ip"] == 1
    assert "hash" in summary_a["by_type"]


def test_shortest_path_finds_direct_link(db_session, org_fixture, build_alert):
    alert = build_alert(org_id=org_fixture.id)
    entity_graph.index_alert(db_session, alert)
    db_session.commit()

    ips = db_session.query(Entity).filter(Entity.entity_type == "ip").all()
    hashes = db_session.query(Entity).filter(Entity.entity_type == "hash").all()
    assert len(ips) >= 1 and len(hashes) >= 1

    result = entity_graph.shortest_path(db_session, ips[0].id, hashes[0].id, org_id=org_fixture.id)
    assert result["reachable"] is True
    assert result["hops"] == 1
    assert len(result["path"]) == 2
    assert len(result["links"]) == 1


def test_shortest_path_returns_empty_when_unreachable(db_session, org_fixture):
    a = entity_graph.upsert_entity(db_session, "ip", "192.0.2.1", org_fixture.id)
    b = entity_graph.upsert_entity(db_session, "ip", "192.0.2.2", org_fixture.id)
    db_session.commit()
    result = entity_graph.shortest_path(db_session, a.id, b.id, org_id=org_fixture.id)
    assert result["reachable"] is False
    assert result["path"] == []
    assert result["hops"] is None


def test_shortest_path_self_is_zero_hops(db_session, org_fixture):
    a = entity_graph.upsert_entity(db_session, "ip", "192.0.2.10", org_fixture.id)
    db_session.commit()
    result = entity_graph.shortest_path(db_session, a.id, a.id, org_id=org_fixture.id)
    assert result["reachable"] is True
    assert result["hops"] == 0


def test_shortest_path_two_hop(db_session, org_fixture):
    """a -> b -> c should yield a 2-hop path through b."""
    a = entity_graph.upsert_entity(db_session, "ip", "192.0.2.20", org_fixture.id)
    b = entity_graph.upsert_entity(db_session, "ip", "192.0.2.21", org_fixture.id)
    c = entity_graph.upsert_entity(db_session, "ip", "192.0.2.22", org_fixture.id)
    alert = SecurityAlert(
        alert_type="system_log",
        source_ip="192.0.2.20",
        severity="LOW",
        score=0.1,
        message=f"flow from {b.value}",
        org_id=org_fixture.id,
    )
    db_session.add(alert)
    db_session.flush()
    entity_graph.link_entities(db_session, a, b, alert, "communicates")
    entity_graph.link_entities(db_session, b, c, alert, "communicates")
    db_session.commit()

    result = entity_graph.shortest_path(db_session, a.id, c.id, org_id=org_fixture.id)
    assert result["reachable"] is True
    assert result["hops"] == 2
    assert [n["value"] for n in result["path"]] == ["192.0.2.20", "192.0.2.21", "192.0.2.22"]