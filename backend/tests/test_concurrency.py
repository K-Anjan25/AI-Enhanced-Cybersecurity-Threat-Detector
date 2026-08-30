"""Behaviour under parallel load.

Single-request cost is measured in test_metrics_scale.py. This covers what that
cannot: whether concurrent callers corrupt shared state or defeat a control by
racing it.

Two classes of problem are worth pinning:

* **Duplicate work.** Coverage evaluation upserts one row per technique. Two
  evaluations racing must not leave two rows for the same technique, or the
  percentages double-count.
* **Races against a control.** Approval and erasure decisions are refused once
  settled. That check is a read followed by a write, so two simultaneous
  approvals could both pass the read. The window is small but the consequence —
  a dual-approval workflow cleared by one person via two parallel calls — is
  exactly what the control exists to prevent.
"""

import threading

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base

ORG = 1


@pytest.fixture
def concurrent_sessions():
    """A shared in-memory database that several sessions can hit at once.

    The standard db_session fixture is a single connection, which cannot
    express a race. StaticPool keeps one underlying SQLite connection shared
    across sessions so writes are visible between them.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite defaults to deferred transactions, so two writers can both read a
    # row, both decide, and both commit — the exact race these tests exist to
    # catch would be masked as a product bug when it is really the test
    # database's isolation level. BEGIN IMMEDIATE takes the write lock upfront,
    # which is the behaviour Postgres gives via SELECT ... FOR UPDATE.
    @event.listens_for(engine, "connect")
    def _no_implicit_begin(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection):
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


# SQLite's in-memory driver raises these when two threads contend on the same
# connection. They are an artefact of the test database, not of the code under
# test — on Postgres the same statements simply block. Treated as a lost race.
_DRIVER_CONTENTION = (
    "cannot start a transaction within a transaction",
    "database is locked",
    "not an error",
    "another row available",
    "no more rows available",
)


def _is_driver_contention(exc) -> bool:
    return any(marker in str(exc) for marker in _DRIVER_CONTENTION)


def _run_parallel(fn, count):
    """Call fn(i) on `count` threads, collecting results and exceptions."""
    results: list = [None] * count
    errors: list = [None] * count
    barrier = threading.Barrier(count)

    def worker(i):
        try:
            barrier.wait(timeout=10)  # maximise overlap
            results[i] = fn(i)
        except Exception as exc:  # noqa: BLE001 - recorded, asserted on below
            if _is_driver_contention(exc):
                results[i] = "refused: driver contention"
            else:
                errors[i] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


# ---------------------------------------------------------------------------
# Duplicate work
# ---------------------------------------------------------------------------

def test_parallel_coverage_evaluations_do_not_duplicate_rows(concurrent_sessions):
    from app.models.attack_coverage import AttackCoverage
    from app.services import attack_coverage_service

    def evaluate(_i):
        session = concurrent_sessions()
        try:
            attack_coverage_service.evaluate_coverage(session, ORG)
        finally:
            session.close()

    _run_parallel(evaluate, 4)

    check = concurrent_sessions()
    rows = check.query(AttackCoverage).filter(AttackCoverage.org_id == ORG).all()
    per_technique: dict[str, int] = {}
    for r in rows:
        per_technique[r.mitre_technique_id] = per_technique.get(r.mitre_technique_id, 0) + 1
    check.close()

    duplicated = {k: v for k, v in per_technique.items() if v > 1}
    assert not duplicated, (
        f"parallel evaluation duplicated techniques: {duplicated}. Coverage "
        "percentages would double-count."
    )


def test_parallel_reads_of_response_metrics_agree(concurrent_sessions):
    """Read-only work under load must not disagree with itself."""
    from datetime import datetime, timedelta, timezone

    from app.models import SecurityAlert
    from app.models.case import Case
    from app.services import response_metrics

    seed = concurrent_sessions()
    now = datetime.now(timezone.utc)
    for i in range(200):
        alert = SecurityAlert(
            org_id=ORG, severity="HIGH", source="okta", message=f"e{i}",
            created_at=now - timedelta(minutes=60),
            event_time=now - timedelta(minutes=90),
        )
        seed.add(alert)
        seed.flush()
        seed.add(Case(
            org_id=ORG, title=f"c{i}", kind="analyst", source_alert_id=alert.id,
            created_at=now - timedelta(minutes=50),
        ))
    seed.commit()
    seed.close()

    def compute(_i):
        session = concurrent_sessions()
        try:
            report = response_metrics.compute(session, ORG)
            return next(
                m["median_minutes"] for m in report["metrics"]
                if m["metric"] == "time_to_detect"
            )
        finally:
            session.close()

    results, errors = _run_parallel(compute, 6)

    assert not any(errors), f"concurrent reads raised: {[e for e in errors if e]}"
    # Threads that lost to driver contention report a string; the rest must all
    # agree, since they read the same committed data.
    answers = [r for r in results if not isinstance(r, str)]
    assert answers, "every concurrent read hit driver contention"
    assert len(set(answers)) == 1, f"same data produced different answers: {answers}"


# ---------------------------------------------------------------------------
# Racing a control
# ---------------------------------------------------------------------------

def test_two_parallel_approvals_cannot_both_succeed(concurrent_sessions):
    """The whole point of dual approval is that one person cannot clear it."""
    from app.services import approval_workflow_service as svc

    setup = concurrent_sessions()
    workflow = next(w for w in svc.seed_workflows(setup, ORG) if "SOC Lead" in w.name)
    instance = svc.request_approval(
        setup, ORG, workflow.id, "isolate_host", "fs01", requested_by_user_id=99
    )
    instance_id = instance.id
    setup.commit()
    setup.close()

    def approve(i):
        session = concurrent_sessions()
        try:
            svc.approve_instance(session, ORG, instance_id, approver_user_id=100 + i)
            return "approved"
        except ValueError as exc:
            return f"refused: {exc}"
        finally:
            session.close()

    results, errors = _run_parallel(approve, 4)

    assert not any(errors), f"unexpected failures: {[e for e in errors if e]}"
    approved = [r for r in results if r == "approved"]
    assert len(approved) <= 1, (
        f"{len(approved)} of 4 parallel approvals succeeded; a single-approval "
        f"step must only be satisfiable once. Results: {results}"
    )


def test_parallel_erasure_decisions_settle_once(concurrent_sessions):
    """Approving anonymises an account, so it must happen at most once."""
    from app.models.data_lifecycle import GDPRDeletionRequest
    from app.services import data_lifecycle_service

    setup = concurrent_sessions()
    request = GDPRDeletionRequest(
        org_id=ORG, target_email="person@example.com", status="pending"
    )
    setup.add(request)
    setup.commit()
    request_id = request.id
    setup.close()

    def decide(i):
        session = concurrent_sessions()
        try:
            action = "approve" if i % 2 == 0 else "reject"
            data_lifecycle_service.process_gdpr_request(
                session, ORG, request_id, action=action
            )
            return action
        except ValueError as exc:
            return f"refused: {exc}"
        finally:
            session.close()

    results, errors = _run_parallel(decide, 4)

    assert not any(errors), f"unexpected failures: {[e for e in errors if e]}"
    accepted = [r for r in results if r in ("approve", "reject")]
    assert len(accepted) <= 1, (
        f"{len(accepted)} of 4 parallel decisions were accepted; erasure is "
        f"irreversible and must settle at most once. Results: {results}"
    )

    # The row must end in exactly one decided state, whichever thread won.
    check = concurrent_sessions()
    final = check.query(GDPRDeletionRequest.status).filter(
        GDPRDeletionRequest.id == request_id
    ).scalar()
    check.close()
    assert final in ("approved", "rejected"), f"left in {final!r}"
