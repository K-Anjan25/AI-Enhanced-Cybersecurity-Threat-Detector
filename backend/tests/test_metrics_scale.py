"""The metrics paths must stay usable as a tenant fills up.

Correctness was well covered; cost was not. Measured at 26k alerts, coverage
evaluation took 66 seconds — it loaded every alert into memory and rescanned
that list once per technique, then issued one SELECT per technique to upsert.
Both are now single queries. These tests pin the shape of the work rather than
a wall-clock number, which would be flaky on shared hardware.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import event

from app.models import Asset, SecurityAlert
from app.models.case import Case

ORG = 1


def _seed(db, *, alerts: int, cases: int = 0) -> None:
    now = datetime.now(timezone.utc)
    db.bulk_save_objects([
        SecurityAlert(
            org_id=ORG, severity="HIGH", source="okta", message=f"e{i}",
            source_ip=f"203.0.113.{i % 250}",
            mitre_technique_id="T1078" if i % 3 == 0 else "T1190",
            created_at=now - timedelta(minutes=i % 5000),
            event_time=now - timedelta(minutes=(i % 5000) + 30),
        )
        for i in range(alerts)
    ])
    db.commit()
    if cases:
        ids = [r.id for r in db.query(SecurityAlert.id).limit(cases).all()]
        db.bulk_save_objects([
            Case(
                org_id=ORG, title=f"c{i}", kind="analyst", source_alert_id=ids[i],
                created_at=now - timedelta(minutes=(i % 5000) - 5),
                decision="approved" if i % 2 else "pending",
                decided_at=(now - timedelta(minutes=(i % 5000) - 20)) if i % 2 else None,
            )
            for i in range(min(cases, len(ids)))
        ])
        db.commit()


class _QueryCounter:
    """Counts SQL statements issued inside the block."""

    def __init__(self, session):
        self.session = session
        self.count = 0

    def __enter__(self):
        self._listener = lambda *a, **kw: setattr(self, "count", self.count + 1)
        event.listen(self.session.get_bind(), "before_cursor_execute", self._listener)
        return self

    def __exit__(self, *exc):
        event.remove(self.session.get_bind(), "before_cursor_execute", self._listener)
        return False


def test_coverage_query_count_does_not_grow_with_techniques(db_session):
    """One SELECT per technique, twice over, was the whole problem."""
    from app.services import attack_coverage_service

    _seed(db_session, alerts=500)

    # Prime: the first run inserts rows, so measure the steady state.
    attack_coverage_service.evaluate_coverage(db_session, ORG)

    with _QueryCounter(db_session) as counter:
        rows = attack_coverage_service.evaluate_coverage(db_session, ORG)

    assert len(rows) >= 14, "should still evaluate every tracked technique"
    assert counter.count < 15, (
        f"{counter.count} queries for {len(rows)} techniques — the per-technique "
        "SELECT is back"
    )


def test_coverage_does_not_load_every_alert(db_session):
    """Detection counts come from a grouped count, not a full table scan."""
    from app.services import attack_coverage_service

    _seed(db_session, alerts=2000)
    rows = attack_coverage_service.evaluate_coverage(db_session, ORG)

    counted = {r.mitre_technique_id: r.detection_count for r in rows}
    # 2000 alerts: every third is T1078 (667), the rest T1190 (1333).
    assert counted["T1078"] == 667
    assert counted["T1190"] == 1333


def test_coverage_is_stable_across_repeated_runs(db_session):
    """Re-evaluating must update in place, not accumulate duplicate rows."""
    from app.models.attack_coverage import AttackCoverage
    from app.services import attack_coverage_service

    _seed(db_session, alerts=100)
    attack_coverage_service.evaluate_coverage(db_session, ORG)
    first = db_session.query(AttackCoverage).filter(AttackCoverage.org_id == ORG).count()

    attack_coverage_service.evaluate_coverage(db_session, ORG)
    second = db_session.query(AttackCoverage).filter(AttackCoverage.org_id == ORG).count()

    assert first == second


def test_response_metrics_run_at_tenant_scale(db_session):
    """Correctness at volume — the numbers must survive 10k cases."""
    from app.services import response_metrics

    _seed(db_session, alerts=10_000, cases=4_000)
    report = response_metrics.compute(db_session, ORG)

    triage = next(m for m in report["metrics"] if m["metric"] == "time_to_triage")
    assert triage["sample_size"] > 0
    assert triage["reliable"] is True
    assert 0 <= triage["median_minutes"] <= triage["slowest_minutes"]

    detect = next(m for m in report["metrics"] if m["metric"] == "time_to_detect")
    assert detect["sample_size"] > 0
    assert abs(detect["median_minutes"] - 30.0) < 1.0, "seeded a 30-minute lag"


def test_reasoning_stays_cheap_on_a_busy_source(db_session):
    """The correlation query is capped, so one noisy IP cannot dominate."""
    from app.services import verdict_reasoning

    _seed(db_session, alerts=5_000, cases=10)
    db_session.add_all([
        Asset(org_id=ORG, name=f"h{i}", asset_type="host", criticality=3)
        for i in range(200)
    ])
    db_session.commit()

    case = db_session.query(Case).first()
    with _QueryCounter(db_session) as counter:
        report = verdict_reasoning.explain(db_session, case)

    assert report["confidence"] is not None
    assert counter.count < 25, f"{counter.count} queries to explain one case"
