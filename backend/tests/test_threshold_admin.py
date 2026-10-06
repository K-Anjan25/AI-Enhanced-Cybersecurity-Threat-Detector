"""T-410: hand-set thresholds and the 7-day impact preview (design.md §4.8, FR-18).

The panel's two jobs, and each is asserted where it could be wrong silently:

**A manual edit cannot leave the bands crossed.** One value is written per
``(family, band)``, so an edit is checked against the other three -- by handing the
substituted set to ``SeverityBands`` itself, the object that bands a score. The test
that matters asserts a *refusal* and then reads the store back: a cross that was
written and repaired would pass a weaker test that only looked at the status code.

**The preview counts recorded alerts, and says what it counted.** The correlator
creates a case for every window it decides exists and bands it afterwards (T-308),
so a count over stored rows is exact for the window rather than an extrapolation.
The tests exercise both directions -- raising a bar (rows that would stop firing)
and lowering one (rows that would start) -- the family filter, and the page cap that
turns a walk that stopped early into ``complete=False`` instead of a total.

**A no-op is not a change.** The same hand setting the same value writes nothing and
audits nothing (D-038); the same value from a *different* provenance is a change,
because the provenance is part of what is being set.

Who may write is R-53's business and is asserted here too: reading a threshold is
every role's, setting one is admin's, and a missing seam fails loudly rather than
reporting a quiet zero.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.main import create_app
from app.services.alert_store import InMemoryAlertStore
from app.services.audit_log import AuditAction, AuditRecord, InMemoryAuditTrail
from app.services.recalibration import (
    BAND_DEFAULTS,
    RECALIBRATED_SOURCE,
    InMemoryThresholdStore,
    ThresholdKey,
    ThresholdRecord,
    UnfittableBand,
)
from app.services.threshold_admin import (
    MANUAL_SOURCE,
    BandOrderRefused,
    InvalidThreshold,
    ThresholdAdminService,
    ThresholdImpactReader,
    last_change,
    source_label,
)
from fastapi.testclient import TestClient

SECRET = "s" * 48
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
FAMILY = "lateral-movement"
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def seeded(*records: ThresholdRecord) -> InMemoryThresholdStore:
    """A store holding exactly ``records``."""
    store = InMemoryThresholdStore()
    for record in records:
        store.put(record)
    return store


def stored(
    family: str = FAMILY, band: str = "high", value: float = 0.8, source: str = MANUAL_SOURCE
):
    """One stored row."""
    return ThresholdRecord(
        key=ThresholdKey(tenant_id="default", family=family, band=band),
        value=value,
        source=source,
        updated_at=NOW - timedelta(hours=1),
    )


def alerts_with(
    scores: list[float], *, family: str = FAMILY, at: datetime | None = None
) -> InMemoryAlertStore:
    """An alert store holding one case per score."""
    store = InMemoryAlertStore()
    moment = at if at is not None else NOW - timedelta(days=1)
    for index, score in enumerate(scores):
        store.save(
            f"case-{family}-{index}",
            {
                "entity_id": 1,
                "family": family,
                "severity": "high",
                "score": Decimal(str(score)),
                "window_ref": {"store": "stream", "id": f"case-{index}"},
                "explanation": {},
                "status": "open",
                "first_seen": moment + timedelta(seconds=index),
                "last_seen": moment + timedelta(seconds=index),
                "occurrence_count": 1,
            },
            created_at=moment + timedelta(seconds=index),
        )
    return store


# --- the rules, without HTTP -------------------------------------------------


def test_a_manual_set_writes_the_value_with_manual_provenance() -> None:
    """The write names its source, which is R-69's provenance column."""
    store = InMemoryThresholdStore()
    admin = ThresholdAdminService(store=store, tenant_id="default")

    write = admin.set_manual(family=FAMILY, band="high", value=0.8, actor="ana", at=NOW)

    assert write.changed is True
    assert write.previous == BAND_DEFAULTS["high"]  # the default was in force
    assert write.previous_label == "default"
    record = store.get(ThresholdKey(tenant_id="default", family=FAMILY, band="high"))
    assert record is not None
    assert record.value == 0.8
    assert record.source == MANUAL_SOURCE
    assert source_label(record.source) == "manual"


def test_a_manual_set_that_would_invert_the_bands_is_refused_and_changes_nothing() -> None:
    """The check is ``SeverityBands``' own rule, applied to the substituted set."""
    store = InMemoryThresholdStore()
    admin = ThresholdAdminService(store=store, tenant_id="default")

    # FR-13 bands are critical 0.90 > high 0.75 > medium 0.55 > low 0.35. Setting
    # `medium` above `high` would leave the family unbandable.
    with pytest.raises(BandOrderRefused) as refusal:
        admin.set_manual(family=FAMILY, band="medium", value=0.8, actor="ana", at=NOW)

    assert "strictly descending" in str(refusal.value)
    assert FAMILY in str(refusal.value)
    assert store.rows() == ()  # nothing was written and nothing was repaired


def test_a_manual_set_may_still_move_a_band_within_its_neighbours() -> None:
    """The rule refuses a crossing, not a change."""
    store = InMemoryThresholdStore()
    admin = ThresholdAdminService(store=store, tenant_id="default")

    admin.set_manual(family=FAMILY, band="medium", value=0.6, actor="ana", at=NOW)
    admin.set_manual(family=FAMILY, band="high", value=0.8, actor="ana", at=NOW)

    assert admin.values_in_force(FAMILY)["medium"] == 0.6
    assert admin.values_in_force(FAMILY)["high"] == 0.8


def test_a_manual_edit_is_checked_against_the_rows_rather_than_the_defaults() -> None:
    """A calibrated row that moved a neighbour is what the edit must not cross."""
    store = seeded(
        ThresholdRecord(
            key=ThresholdKey(tenant_id="default", family=FAMILY, band="low"),
            value=0.5,
            source=RECALIBRATED_SOURCE,
            updated_at=NOW - timedelta(days=2),
        )
    )
    admin = ThresholdAdminService(store=store, tenant_id="default")

    # Against the defaults this would be legal (0.55 > 0.45 > 0.35); against the
    # recalibrated `low` of 0.5 it is a crossing, and the row is the authority.
    with pytest.raises(BandOrderRefused):
        admin.set_manual(family=FAMILY, band="medium", value=0.45, actor="ana", at=NOW)


def test_a_repeat_from_the_same_hand_is_not_a_change() -> None:
    """Nothing is written and nothing will be audited."""
    store = seeded(stored(value=0.8))
    admin = ThresholdAdminService(store=store, tenant_id="default")

    write = admin.set_manual(family=FAMILY, band="high", value=0.8, actor="ana", at=NOW)

    assert write.changed is False
    assert write.previous == 0.8


def test_the_same_value_from_a_different_provenance_is_a_change() -> None:
    """Provenance is part of what a manual set decides."""
    store = seeded(stored(value=0.8, source=RECALIBRATED_SOURCE))
    admin = ThresholdAdminService(store=store, tenant_id="default")

    write = admin.set_manual(family=FAMILY, band="high", value=0.8, actor="ana", at=NOW)

    assert write.changed is True
    record = store.get(ThresholdKey(tenant_id="default", family=FAMILY, band="high"))
    assert record is not None
    assert record.source == MANUAL_SOURCE
    assert write.previous_label == "calibrated"


def test_a_value_outside_the_open_unit_interval_is_refused() -> None:
    """A proportion, checked before the store is touched."""
    admin = ThresholdAdminService(store=InMemoryThresholdStore(), tenant_id="default")
    for value in (0.0, 1.0, -0.2, 1.4):
        with pytest.raises(InvalidThreshold):
            admin.set_manual(family=FAMILY, band="high", value=value, actor="ana", at=NOW)


def test_the_info_band_has_no_bound_to_move() -> None:
    """FR-13 gives ``info`` no lower bound, so there is no number to set."""
    admin = ThresholdAdminService(store=InMemoryThresholdStore(), tenant_id="default")
    with pytest.raises(UnfittableBand):
        admin.set_manual(family=FAMILY, band="info", value=0.2, actor="ana", at=NOW)


def test_attribution_comes_from_the_trail_at_the_rows_own_instant() -> None:
    """The writer of a row and the writer in the trail are the same event."""
    store = seeded(stored())
    trail = InMemoryAuditTrail()

    trail.append(
        AuditRecord(
            action=AuditAction.threshold_set,
            actor="ana@corp",
            target_type="threshold",
            target_id=str(store.rows()[0].key),
            at=store.rows()[0].updated_at,
            detail={"previous": 0.75, "applied": 0.8},
        )
    )

    change = last_change(trail, store.rows()[0].key, at=store.rows()[0].updated_at)

    assert change is not None
    assert change.actor == "ana@corp"
    assert change.previous == 0.75
    assert change.applied == 0.8


def test_attribution_is_none_rather_than_guessed_when_the_trail_is_empty() -> None:
    """A missing record is a fact the screen renders, not a reason to invent an actor."""
    row = stored()
    assert last_change(InMemoryAuditTrail(), row.key, at=row.updated_at) is None


# --- the preview -------------------------------------------------------------


def reader(
    scores: list[float], *, band: str = "high", value: float = 0.75, **extra: Any
) -> ThresholdImpactReader:
    """A reader over a store holding ``scores`` and one manual row."""
    admin = ThresholdAdminService(store=seeded(stored(band=band, value=value)), tenant_id="default")
    return ThresholdImpactReader(alerts=alerts_with(scores), admin=admin, **extra)


def test_raising_a_bar_counts_what_would_stop_firing() -> None:
    """The direction FR-18's false-positive budget moves."""
    impact = reader([0.95, 0.85, 0.8, 0.7, 0.2], value=0.7).preview(
        family=FAMILY, band="high", proposed=0.8, at=NOW
    )

    assert impact.alerts_read == 5
    # At or above, not above: the bound is a boundary, as FR-13's bands are.
    assert impact.would_fire == 3  # 0.95, 0.85 and 0.8
    assert impact.would_stop_firing == 1  # 0.7 cleared the current bar and would not
    assert impact.would_start_firing == 0
    assert impact.current == 0.7
    assert impact.current_label == "manual"
    assert impact.complete is True


def test_lowering_a_bar_counts_what_would_start_firing() -> None:
    """A lower bar pulls in the cases that were recorded but banded lower."""
    impact = reader([0.95, 0.8, 0.6, 0.5], value=0.8).preview(
        family=FAMILY, band="high", proposed=0.55, at=NOW
    )

    assert impact.would_fire == 3
    assert impact.would_start_firing == 1  # 0.6; 0.5 is still below the proposal
    assert impact.would_stop_firing == 0


def test_the_window_is_exactly_the_seven_days_ending_now() -> None:
    """design.md §4.8's window, reported rather than assumed."""
    impact = reader([0.9]).preview(family=FAMILY, band="high", proposed=0.8, at=NOW)

    assert impact.window_end == NOW
    assert impact.window_start == NOW - timedelta(days=7)


def test_only_the_family_being_edited_is_counted() -> None:
    """A threshold is keyed by family, so a count across families answers nothing."""
    store = InMemoryAlertStore()
    for family, score in ((FAMILY, 0.95), (FAMILY, 0.9), ("exfiltration", 0.99)):
        store.save(
            f"case-{family}-{score}",
            {
                "entity_id": 1,
                "family": family,
                "severity": "high",
                "score": Decimal(str(score)),
                "window_ref": {},
                "explanation": {},
                "status": "open",
                "first_seen": NOW - timedelta(days=1),
                "last_seen": NOW - timedelta(days=1),
                "occurrence_count": 1,
            },
            created_at=NOW - timedelta(days=1),
        )
    admin = ThresholdAdminService(store=seeded(stored(value=0.7)), tenant_id="default")

    impact = ThresholdImpactReader(alerts=store, admin=admin).preview(
        family=FAMILY, band="high", proposed=0.8, at=NOW
    )

    assert impact.alerts_read == 2
    assert impact.would_fire == 2


def test_a_walk_that_hits_the_page_cap_is_not_reported_as_a_total() -> None:
    """``complete=False`` is the difference between a floor and a count."""
    impact = reader([0.95] * 5, value=0.7, page_size=2, max_pages=2).preview(
        family=FAMILY, band="high", proposed=0.8, at=NOW
    )

    assert impact.complete is False
    assert impact.alerts_read == 4  # two pages of two, walked, then stopped
    assert impact.would_fire == 4


def test_a_family_with_no_row_is_previewed_against_the_documented_default() -> None:
    """Never against zero, which would make every count look like an improvement."""
    admin = ThresholdAdminService(store=InMemoryThresholdStore(), tenant_id="default")
    impact = ThresholdImpactReader(alerts=alerts_with([0.8, 0.4]), admin=admin).preview(
        family="brand-new", band="high", proposed=0.8, at=NOW
    )

    assert impact.current == BAND_DEFAULTS["high"]
    assert impact.current_label == "default"


def test_the_preview_refuses_what_the_writer_refuses() -> None:
    """One rule for the value, whichever route asks."""
    admin = ThresholdAdminService(store=InMemoryThresholdStore(), tenant_id="default")
    impact = ThresholdImpactReader(alerts=alerts_with([]), admin=admin)
    with pytest.raises(UnfittableBand):
        impact.preview(family=FAMILY, band="info", proposed=0.5, at=NOW)
    with pytest.raises(InvalidThreshold):
        impact.preview(family=FAMILY, band="high", proposed=1.5, at=NOW)


# --- through HTTP ------------------------------------------------------------


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        service_name="aegis-backend-test",
        secret_key=APP_SECRET,
        log_level="WARNING",
    )


def build(settings: Settings, auth: TokenService, **state: Any) -> TestClient:
    """The real application, with any state seam a test wants to replace."""
    app = create_app(settings)
    app.state.token_service = auth
    for name, value in state.items():
        setattr(app.state, name, value)
    return TestClient(app)


def headers(auth: TokenService, role: str = "admin", subject: str | None = None) -> dict[str, str]:
    """An Authorization header for one role."""
    pair = auth.issue(subject if subject is not None else f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def wire(client: TestClient, *, store: InMemoryThresholdStore, alerts: Any = None) -> None:
    """Point every threshold seam at one store, the way ``main.py`` wires them.

    Three services read the same store -- the recalibration job, the listing and the
    hand-set panel -- and a test that replaced only one of them would be asserting
    against a different store than the route wrote through, which is a passing test
    about nothing.
    """
    client.app.state.threshold_store = store  # type: ignore[attr-defined]
    client.app.state.recalibration = replace(  # type: ignore[attr-defined]
        client.app.state.recalibration, store=store  # type: ignore[attr-defined]
    )
    admin = ThresholdAdminService(store=store, tenant_id="default")
    client.app.state.threshold_admin = admin  # type: ignore[attr-defined]
    client.app.state.threshold_impact = ThresholdImpactReader(  # type: ignore[attr-defined]
        alerts=alerts if alerts is not None else client.app.state.alert_store, admin=admin  # type: ignore[attr-defined]
    )


def audit_rows(client: TestClient, action: AuditAction) -> list[Any]:
    """The audit entries this test's requests produced, for one action."""
    trail: InMemoryAuditTrail = client.app.state.audit_trail  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    return [
        entry
        for entry in trail.entries(start=now - timedelta(hours=1), end=now + timedelta(hours=1))
        if entry.record.action is action
    ]


def test_the_admin_panel_reads_the_listing_with_provenance_and_attribution(
    settings: Settings, auth: TokenService
) -> None:
    """design.md §4.8's four columns: value, source, changed by, changed at."""
    trail = InMemoryAuditTrail()
    store = InMemoryThresholdStore()
    with build(settings, auth, audit_trail=trail) as client:
        wire(client, store=store)
        token = headers(client.app.state.token_service, "admin", "ana@corp.example")  # type: ignore[attr-defined]
        written = client.put(
            f"/api/v1/thresholds/{FAMILY}/high",
            json={"value": 0.8},
            headers=token,
        )
        listing = client.get("/api/v1/thresholds", headers=token)

    assert written.status_code == 200
    assert written.json()["previous"] == BAND_DEFAULTS["high"]
    assert written.json()["previous_label"] == "default"
    assert written.json()["applied"] == 0.8
    assert written.json()["source"] == MANUAL_SOURCE
    assert written.json()["changed"] is True

    rows = [row for row in listing.json()["items"] if row["family"] == FAMILY]
    assert len(rows) == 1
    assert rows[0]["source"] == MANUAL_SOURCE
    assert rows[0]["source_label"] == "manual"
    assert rows[0]["changed_by"] == "ana@corp.example"
    assert listing.json()["defaults"] == dict(BAND_DEFAULTS)

    # The attribution is the row's own write, recorded once.
    assert len(audit_rows(client, AuditAction.threshold_set)) == 1


def test_a_calibrated_row_reads_as_calibrated(settings: Settings, auth: TokenService) -> None:
    """T-322's provenance survives the hand-set panel's vocabulary."""
    store = seeded(
        ThresholdRecord(
            key=ThresholdKey(tenant_id="default", family=FAMILY, band="high"),
            value=0.81,
            source=RECALIBRATED_SOURCE,
            updated_at=datetime.now(UTC) - timedelta(minutes=5),
        )
    )
    with build(settings, auth) as client:
        wire(client, store=store)
        listing = client.get(
            "/api/v1/thresholds",
            headers=headers(client.app.state.token_service, "viewer"),  # type: ignore[attr-defined]
        )

    row = next(row for row in listing.json()["items"] if row["family"] == FAMILY)
    assert row["source"] == RECALIBRATED_SOURCE
    assert row["source_label"] == "calibrated"
    assert row["changed_by"] is None  # no matching trail record in this app


def test_an_inverting_manual_set_is_a_409_with_the_bands_named(
    settings: Settings, auth: TokenService
) -> None:
    """A conflict with the values in force, not a malformed request."""
    with build(settings, auth) as client:
        response = client.put(
            f"/api/v1/thresholds/{FAMILY}/medium",
            json={"value": 0.95},
            headers=headers(client.app.state.token_service, "admin"),  # type: ignore[attr-defined]
        )

    assert response.status_code == 409
    assert "strictly descending" in response.json()["detail"]
    assert audit_rows(client, AuditAction.threshold_set) == []


def test_a_value_that_is_not_a_proportion_is_refused_at_the_edge(
    settings: Settings, auth: TokenService
) -> None:
    """The schema bounds it, so a units mistake never reaches the service."""
    with build(settings, auth) as client:
        token = headers(client.app.state.token_service, "admin")  # type: ignore[attr-defined]
        high = client.put(f"/api/v1/thresholds/{FAMILY}/high", json={"value": 70}, headers=token)
        zero = client.put(f"/api/v1/thresholds/{FAMILY}/high", json={"value": 0}, headers=token)

    assert high.status_code == 422
    assert zero.status_code == 422


def test_the_info_band_is_a_400_with_the_bands_that_have_bounds(
    settings: Settings, auth: TokenService
) -> None:
    """``info`` has nothing to set, and the allowed bands are named."""
    with build(settings, auth) as client:
        response = client.put(
            "/api/v1/thresholds/some-family/info",
            json={"value": 0.2},
            headers=headers(client.app.state.token_service, "admin"),  # type: ignore[attr-defined]
        )

    assert response.status_code == 400
    assert "high" in response.json()["detail"]


def test_the_preview_route_returns_the_counts_and_the_window(
    settings: Settings, auth: TokenService
) -> None:
    """The panel's number arrives with the window that produced it."""
    store = InMemoryAlertStore()
    now = datetime.now(UTC)
    for index, score in enumerate([0.95, 0.85, 0.78]):
        store.save(
            f"case-{index}",
            {
                "entity_id": 1,
                "family": FAMILY,
                "severity": "high",
                "score": Decimal(str(score)),
                "window_ref": {},
                "explanation": {},
                "status": "open",
                "first_seen": now - timedelta(days=1),
                "last_seen": now - timedelta(days=1),
                "occurrence_count": 1,
            },
            created_at=now - timedelta(days=1),
        )
    with build(settings, auth) as client:
        wire(client, store=InMemoryThresholdStore(), alerts=store)
        response = client.get(
            "/api/v1/thresholds/preview",
            params={"family": FAMILY, "band": "high", "value": 0.8},
            headers=headers(client.app.state.token_service, "analyst"),  # type: ignore[attr-defined]
        )

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "default"
    assert body["proposed"] == 0.8
    assert body["current"] == BAND_DEFAULTS["high"]
    assert body["current_source"] == "default"
    assert body["alerts_read"] == 3
    assert body["would_fire"] == 2
    assert body["would_stop_firing"] == 1
    assert body["complete"] is True
    window = datetime.fromisoformat(body["window_end"]) - datetime.fromisoformat(
        body["window_start"]
    )
    assert window == timedelta(days=7)


def test_the_preview_is_readable_by_every_role_and_writes_nothing(
    settings: Settings, auth: TokenService
) -> None:
    """Reading a bar is reading: an analyst asks what a different bar would have done."""
    with build(settings, auth) as client:
        for role in ("viewer", "analyst", "responder", "admin"):
            response = client.get(
                "/api/v1/thresholds/preview",
                params={"family": FAMILY, "band": "high", "value": 0.8},
                headers=headers(client.app.state.token_service, role),  # type: ignore[attr-defined]
            )
            assert response.status_code == 200
        assert (
            client.get(
                "/api/v1/thresholds/preview",
                params={"family": FAMILY, "band": "high", "value": 0.8},
            ).status_code
            == 401
        )

    assert audit_rows(client, AuditAction.threshold_set) == []
    assert audit_rows(client, AuditAction.threshold_recalibrate) == []


def test_setting_a_threshold_is_admin_only(settings: Settings, auth: TokenService) -> None:
    """R-53's ``models`` capability, because moving a bar changes what fires."""
    with build(settings, auth) as client:
        for role in ("viewer", "analyst", "responder"):
            response = client.put(
                f"/api/v1/thresholds/{FAMILY}/high",
                json={"value": 0.8},
                headers=headers(client.app.state.token_service, role),  # type: ignore[attr-defined]
            )
            assert response.status_code == 403
        assert (
            client.put(f"/api/v1/thresholds/{FAMILY}/high", json={"value": 0.8}).status_code == 401
        )


def test_a_missing_seam_fails_loudly(settings: Settings, auth: TokenService) -> None:
    """The preview must not answer zero when nothing is wired to count over."""
    with build(settings, auth) as client:
        del client.app.state.threshold_impact  # type: ignore[attr-defined]
        token = headers(client.app.state.token_service, "admin")  # type: ignore[attr-defined]
        with pytest.raises(RuntimeError, match="threshold_impact"):
            client.get(
                "/api/v1/thresholds/preview",
                params={"family": FAMILY, "band": "high", "value": 0.8},
                headers=token,
            )
