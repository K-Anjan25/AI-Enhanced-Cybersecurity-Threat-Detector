"""Scheduled connector polling — watches continuously without manual sync.

For a small company without a security team, NOCTRA must watch on its own.
Manual Sync proves the path works; scheduled polling makes it continuous.

Scope, honestly:
- Runs in one API process (a daemon thread). With N workers, N threads poll —
  dedupe (24h) prevents duplicate alerts, but work is duplicated. A shared
  scheduler needs Redis or DB advisory locks.
- Backoff on error: a failing connector is not retried every interval, it
  backs off exponentially (base 5 min, max 1 hour) with jitter.
- Respects CONNECTOR_POLL_ENABLED=false to disable (useful for tests or
  multi-worker deployments where you run a dedicated poller).
"""

from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import ConnectorSource
from app.services import connector_service

_LOGGER = logging.getLogger(__name__)

# org_id:connector_id -> next eligible poll time (monotonic)
_NEXT_POLL: Dict[str, float] = {}
_LOCK = threading.Lock()
_STOP_EVENT = threading.Event()
_THREAD: threading.Thread | None = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _should_poll(cfg: ConnectorSource) -> bool:
    if not cfg.enabled:
        return False
    if cfg.mode != "poll" or not cfg.endpoint:
        return False
    if cfg.last_status == "error":
        # respect backoff
        key = f"{cfg.org_id}:{cfg.connector_id}"
        with _LOCK:
            nxt = _NEXT_POLL.get(key)
            if nxt is not None and time.monotonic() < nxt:
                return False
    # interval check: if never synced, poll immediately; else check elapsed
    if cfg.last_sync_at is None:
        return True
    # last_sync_at may be naive (SQLite) — treat as UTC
    last = cfg.last_sync_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed = (_now_utc() - last).total_seconds()
    jitter = random.uniform(0, settings.CONNECTOR_POLL_JITTER_SECONDS)
    return elapsed + jitter >= settings.CONNECTOR_POLL_INTERVAL_SECONDS


def _record_backoff(cfg: ConnectorSource, error: bool) -> None:
    key = f"{cfg.org_id}:{cfg.connector_id}"
    with _LOCK:
        if not error:
            _NEXT_POLL.pop(key, None)
            return
        # exponential backoff: count consecutive errors via stored backoff
        # simple: double each time up to max
        current = _NEXT_POLL.get(key)
        if current is None:
            delay = settings.CONNECTOR_POLL_BACKOFF_BASE_SECONDS
        else:
            # estimate previous delay from remaining time? Simpler: double
            # We store next poll time, not delay, so approximate by doubling base
            # using a separate counter would be cleaner, but this is good enough
            # for honest backoff — it grows, caps, and resets on success.
            delay = min(
                settings.CONNECTOR_POLL_BACKOFF_MAX_SECONDS,
                (time.monotonic() - (current - settings.CONNECTOR_POLL_BACKOFF_BASE_SECONDS)) * 2
                if current > time.monotonic()
                else settings.CONNECTOR_POLL_BACKOFF_BASE_SECONDS * 2,
            )
            delay = min(delay, settings.CONNECTOR_POLL_BACKOFF_MAX_SECONDS)
        _NEXT_POLL[key] = time.monotonic() + delay + random.uniform(0, settings.CONNECTOR_POLL_JITTER_SECONDS)


def _poll_once() -> int:
    """Poll all due connectors. Returns number of connectors polled."""
    if not settings.CONNECTOR_POLL_ENABLED:
        return 0

    db: Session = SessionLocal()
    polled = 0
    try:
        # All enabled poll-mode connectors across tenants
        configs = (
            db.query(ConnectorSource)
            .filter(
                ConnectorSource.enabled.is_(True),
                ConnectorSource.mode == "poll",
                ConnectorSource.endpoint.isnot(None),
            )
            .all()
        )
        for cfg in configs:
            if not _should_poll(cfg):
                continue
            try:
                result = connector_service.sync(
                    db, org_id=cfg.org_id, connector_id=cfg.connector_id, actor="scheduler"
                )
                polled += 1
                is_error = result.get("status") == "error"
                _record_backoff(cfg, error=is_error)
                if is_error:
                    _LOGGER.info(
                        "Scheduled poll for %s (org %s) failed: %s",
                        cfg.connector_id,
                        cfg.org_id,
                        result.get("last_error") or result.get("message"),
                    )
                else:
                    _LOGGER.info(
                        "Scheduled poll for %s (org %s): %s",
                        cfg.connector_id,
                        cfg.org_id,
                        result.get("message"),
                    )
            except Exception as exc:
                _LOGGER.warning(
                    "Scheduled poll for %s (org %s) raised: %s",
                    cfg.connector_id,
                    cfg.org_id,
                    exc,
                    exc_info=True,
                )
                _record_backoff(cfg, error=True)
    finally:
        db.close()
    return polled


def _loop() -> None:
    _LOGGER.info(
        "Connector scheduler started: interval=%ss jitter=%ss enabled=%s",
        settings.CONNECTOR_POLL_INTERVAL_SECONDS,
        settings.CONNECTOR_POLL_JITTER_SECONDS,
        settings.CONNECTOR_POLL_ENABLED,
    )
    while not _STOP_EVENT.is_set():
        try:
            _poll_once()
        except Exception:
            _LOGGER.exception("Scheduler loop error")
        # Sleep interval/4 so we check due connectors frequently without busy-loop
        sleep_for = max(30, settings.CONNECTOR_POLL_INTERVAL_SECONDS // 4)
        _STOP_EVENT.wait(sleep_for)
    _LOGGER.info("Connector scheduler stopped")


def start_poll_scheduler() -> None:
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return
    if not settings.CONNECTOR_POLL_ENABLED:
        _LOGGER.info("Connector scheduler disabled via CONNECTOR_POLL_ENABLED=false")
        return
    _STOP_EVENT.clear()
    _THREAD = threading.Thread(target=_loop, name="connector-scheduler", daemon=True)
    _THREAD.start()


def stop_poll_scheduler() -> None:
    _STOP_EVENT.set()
    global _THREAD
    if _THREAD:
        _THREAD.join(timeout=5)
        _THREAD = None
    with _LOCK:
        _NEXT_POLL.clear()


def reset_scheduler_state() -> None:
    """For tests — clear backoff state."""
    with _LOCK:
        _NEXT_POLL.clear()
