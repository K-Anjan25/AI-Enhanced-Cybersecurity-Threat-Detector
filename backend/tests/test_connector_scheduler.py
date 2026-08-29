"""Scheduled connector polling — watches continuously."""

import pytest

from app.core.config import settings
from app.models import Org, ConnectorSource
from app.services import connector_scheduler


@pytest.fixture(autouse=True)
def _reset_scheduler():
    connector_scheduler.reset_scheduler_state()
    yield
    connector_scheduler.reset_scheduler_state()


@pytest.fixture()
def org(db_session):
    row = Org(name="Acme Inc", slug="acme")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_should_poll_never_synced(db_session, org):
    cfg = ConnectorSource(
        org_id=org.id,
        connector_id="okta",
        name="Okta",
        category="Identity",
        mode="poll",
        endpoint="http://example.com/events.json",
        enabled=True,
        last_sync_at=None,
    )
    db_session.add(cfg)
    db_session.commit()
    assert connector_scheduler._should_poll(cfg) is True


def test_should_poll_respects_interval(db_session, org):
    from datetime import datetime, timezone, timedelta

    cfg = ConnectorSource(
        org_id=org.id,
        connector_id="okta",
        name="Okta",
        category="Identity",
        mode="poll",
        endpoint="http://example.com/events.json",
        enabled=True,
        last_sync_at=datetime.now(timezone.utc) - timedelta(seconds=100),
    )
    db_session.add(cfg)
    db_session.commit()

    # interval is 900s, last sync 100s ago → should NOT poll
    assert connector_scheduler._should_poll(cfg) is False

    # make last sync old enough
    cfg.last_sync_at = datetime.now(timezone.utc) - timedelta(seconds=2000)
    db_session.commit()
    assert connector_scheduler._should_poll(cfg) is True


def test_should_not_poll_disabled_or_push(db_session, org):
    cfg_disabled = ConnectorSource(
        org_id=org.id,
        connector_id="okta",
        name="Okta",
        category="Identity",
        mode="poll",
        endpoint="http://example.com/events.json",
        enabled=False,
    )
    cfg_push = ConnectorSource(
        org_id=org.id,
        connector_id="sentinel",
        name="Sentinel",
        category="Endpoint",
        mode="push",
        endpoint=None,
        enabled=True,
    )
    db_session.add_all([cfg_disabled, cfg_push])
    db_session.commit()
    assert connector_scheduler._should_poll(cfg_disabled) is False
    assert connector_scheduler._should_poll(cfg_push) is False


def test_backoff_on_error(monkeypatch, db_session, org):
    cfg = ConnectorSource(
        org_id=org.id,
        connector_id="okta",
        name="Okta",
        category="Identity",
        mode="poll",
        endpoint="http://example.com/events.json",
        enabled=True,
        last_sync_at=None,
        last_status="error",
    )
    db_session.add(cfg)
    db_session.commit()

    # no backoff yet → should poll
    assert connector_scheduler._should_poll(cfg) is True

    # record error backoff
    connector_scheduler._record_backoff(cfg, error=True)
    # now should NOT poll (backoff active)
    assert connector_scheduler._should_poll(cfg) is False

    # record success clears backoff
    connector_scheduler._record_backoff(cfg, error=False)
    assert connector_scheduler._should_poll(cfg) is True


def test_poll_once_respects_enabled_flag(monkeypatch, db_session):
    monkeypatch.setattr(settings, "CONNECTOR_POLL_ENABLED", False)
    assert connector_scheduler._poll_once() == 0
    monkeypatch.setattr(settings, "CONNECTOR_POLL_ENABLED", True)
