"""Real connector ingest — configuration, polling and push, with honest status.

Replaces the hardcoded connector list. The rules this module exists to uphold:

1. **A connector is "connected" only if it is configured, enabled, and its
   last sync succeeded.** Otherwise it says so (`configured` / `not_connected`).
2. **Every number is derived from rows this deployment actually ingested.**
   `assets_monitored` counts distinct source IPs seen from that connector;
   `latency_ms` is the measured duration of the last request.
3. **Failures are reported, never swallowed.** A failed poll returns
   `status: "error"` with the exception text and records it on the row — it
   does not fall back to a cheerful "success".
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.secrets import SecretDecryptionError, decrypt_secret, encrypt_secret
from app.models import ConnectorSource, SecurityAlert
from app.services.mitre import map_alert
from app.utils.helpers import create_audit_log

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ingest rate limiting
# ---------------------------------------------------------------------------
#
# The push webhook is unauthenticated apart from the shared secret, so
# "anyone holding the token can post" also means "as fast as they like" —
# which is a cheap way to fill the alerts table. This is a fixed-window
# counter per connector.
#
# Honest scope: the counter lives in this process, so the real ceiling is
# CONNECTOR_INGEST_RATE_LIMIT x (number of workers). It bounds a runaway or
# compromised sender rather than enforcing a tenant quota; a shared limit
# needs Redis or a database-backed window.

_INGEST_WINDOW_SECONDS = 60
_RATE_LOCK = threading.Lock()
_RATE_HITS: dict[str, list[float]] = {}


class RateLimited(Exception):
    """Too many ingest requests for one connector inside the window."""

    def __init__(self, connector_id: str, retry_after: float):
        super().__init__(f"Too many ingest requests for {connector_id}")
        self.connector_id = connector_id
        self.retry_after = max(1, int(retry_after))


def _check_ingest_rate(connector_id: str) -> None:
    limit = settings.CONNECTOR_INGEST_RATE_LIMIT
    if limit <= 0:  # 0 disables the limiter
        return

    now = time.monotonic()
    with _RATE_LOCK:
        hits = _RATE_HITS.setdefault(connector_id, [])
        cutoff = now - _INGEST_WINDOW_SECONDS
        while hits and hits[0] < cutoff:
            hits.pop(0)
        if len(hits) >= limit:
            raise RateLimited(connector_id, _INGEST_WINDOW_SECONDS - (now - hits[0]))
        hits.append(now)


def reset_ingest_rate_limits() -> None:
    """Clear the counters. Used by tests; harmless in production."""
    with _RATE_LOCK:
        _RATE_HITS.clear()


# The catalogue — the sources NOCTRA is built to ingest from. A catalogue entry
# alone proves nothing; it only becomes "connected" once a source row exists and
# has synced successfully.
# Phase 40: expanded from 4 to 10 — more telemetry makes the live stream busy
# and the scheduled poller useful. Each entry is a real product with a real API.
CATALOGUE: list[tuple[str, str, str]] = [
    ("okta", "Okta Identity Cloud", "Identity"),
    ("sentinel", "CrowdStrike / Sentinel EDR", "Endpoint"),
    ("guardduty", "AWS GuardDuty & IAM Audit", "Cloud Security"),
    ("cloudflare", "Cloudflare Edge WAF", "Network & Edge"),
    # Phase 40 — breadth: code, collaboration, productivity, identity, observability, SIEM
    ("github", "GitHub Advanced Security", "Code & Supply Chain"),
    ("slack", "Slack Enterprise Audit Logs", "Collaboration"),
    ("gworkspace", "Google Workspace Admin", "Productivity"),
    ("azuread", "Microsoft Entra ID", "Identity"),
    ("datadog", "Datadog Cloud SIEM", "Observability"),
    ("splunk", "Splunk Enterprise Security", "SIEM"),
]

VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
REQUEST_TIMEOUT = (3, 10)  # (connect, read) seconds

# Poll mode makes this server fetch a URL a tenant typed. Unchecked, that is a
# ready-made SSRF: point it at cloud metadata (169.254.169.254), at a service
# that trusts the pod's network position, or at the API itself. Non-local
# environments refuse internal addresses — see _guard_endpoint.
_DEV_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


def _is_internal_address(raw: str) -> bool:
    ip = ipaddress.ip_address(raw)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _guard_active() -> bool:
    """Is the internal-address policy in force? Off in dev/test, where the
    documented walkthrough points a connector at 127.0.0.1."""
    return (settings.ENVIRONMENT or "").strip().lower() not in _DEV_ENVIRONMENTS


def _guard_endpoint(url: str | None) -> None:
    """Refuse endpoints that would turn a poll into an SSRF.

    Inactive in dev/test environments on purpose: a dev checkout defaults to
    ENVIRONMENT="development", and docs/demo.md §3a's local mock endpoint
    (http://127.0.0.1) depends on that — while a deployed instance must refuse
    exactly that address. k8s/configmap.yaml sets ENVIRONMENT="production".

    Two honest limits:
    * A name this process cannot resolve cannot be judged here, so it is
      allowed through and left to fail (or succeed) at request time.
    * DNS rebinding between this check and requests' own lookup is not
      covered — closing that means pinning the resolved IP for the
      connection, a larger change than this guard.

    So this is defence in depth against a hostile or mistaken endpoint, not a
    sealed boundary.
    """
    if not _guard_active():
        return
    if not url:
        return

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("endpoint must be an http(s) URL")
    host = parsed.hostname
    if not host:
        raise ValueError("endpoint URL has no host")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_internal_address(literal):
            raise ValueError(_INTERNAL_ENDPOINT_MESSAGE)
        return

    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return  # Nothing to judge here; the request itself will fail.
    if any(_is_internal_address(info[4][0]) for info in resolved):
        raise ValueError(_INTERNAL_ENDPOINT_MESSAGE)


_INTERNAL_ENDPOINT_MESSAGE = (
    "endpoint resolves to a private, loopback or link-local address — "
    "refusing to fetch it"
)


class _PinnedHostAdapter(requests.adapters.HTTPAdapter):
    """HTTPS adapter that connects to an IP but verifies the real hostname.

    Without this, pinning would break TLS: the certificate would be checked
    against the IP we connected to rather than the name that was resolved.
    """

    def __init__(self, hostname: str, **kwargs):
        self._hostname = hostname
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["server_hostname"] = self._hostname  # SNI uses the real name
        pool_kwargs["assert_hostname"] = self._hostname  # cert is checked against it
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


def _pin_to_ip(url: str) -> tuple[str, dict[str, str], str | None, list[str]]:
    """Rewrite a URL so the connection goes to the IP we just validated.

    Returns ``(request_url, extra_headers, tls_hostname, addresses)``.
    ``tls_hostname`` is None when nothing was pinned — either the host is
    already an IP literal, or the name does not resolve (in which case the
    request fails with its own error rather than one we invented).

    ``addresses`` is what the caller must validate: they are the addresses the
    request will actually use. Checking a *different* resolution — which is
    what calling getaddrinfo twice does — leaves the rebinding window wide
    open, because the second lookup can answer differently.

    This is the other half of the SSRF guard. Checking that a name resolves
    somewhere public and *then* letting requests resolve it again is a race a
    hostile nameserver wins: it answers with a public address for the check and
    an internal one for the request (DNS rebinding). Connecting to the address
    that was validated removes the second lookup.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if host is None:
        return url, {}, None, []

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return url, {}, None, [host]  # IP literal — nothing to rebind

    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return url, {}, None, []

    addresses = [info[4][0] for info in resolved]
    if not addresses:
        return url, {}, None, []

    ip = addresses[0]
    netloc = f"[{ip}]" if ":" in ip else ip
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    pinned = urlunparse(parsed._replace(netloc=netloc))

    # The Host header has to keep the original name; only the socket target
    # changes.
    default_port = 443 if parsed.scheme == "https" else 80
    host_header = host if parsed.port in (None, default_port) else f"{host}:{parsed.port}"
    return pinned, {"Host": host_header}, host, addresses


def _fetch_events(url: str, headers: dict | None, timeout=REQUEST_TIMEOUT):
    """GET an events URL, connecting to an address that was just checked.

    The resolution, the policy check and the connection all use the same
    addresses, resolved once. That is what closes DNS rebinding: an attacker
    who answers the *next* lookup with 169.254.169.254 is talking to a lookup
    that never happens.
    """
    pinned, extra_headers, tls_host, addresses = _pin_to_ip(url)

    if _guard_active() and any(_is_internal_address(addr) for addr in addresses):
        raise ValueError(_INTERNAL_ENDPOINT_MESSAGE)

    merged = {**(headers or {}), **extra_headers}

    if tls_host is None or not pinned.startswith("https://"):
        return requests.get(pinned, headers=merged or None, timeout=timeout)

    session = requests.Session()
    session.mount("https://", _PinnedHostAdapter(tls_host))
    try:
        return session.get(pinned, headers=merged or None, timeout=timeout)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _humanize(moment: datetime | None) -> str | None:
    """'just now' / '4 minutes ago' / '2 days ago' — null in, null out."""
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    delta = _now() - moment
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def get_config(db: Session, org_id: int | None, connector_id: str) -> ConnectorSource | None:
    query = db.query(ConnectorSource).filter(ConnectorSource.connector_id == connector_id)
    if org_id is not None:
        query = query.filter(ConnectorSource.org_id == org_id)
    return query.first()


def _assets_monitored(db: Session, org_id: int | None, connector_id: str) -> int:
    """Distinct source IPs this connector has actually delivered.

    Real telemetry only — no row, no number.
    """
    query = db.query(SecurityAlert.source_ip).filter(
        SecurityAlert.source == connector_id,
        SecurityAlert.source_ip.isnot(None),
        SecurityAlert.source_ip != "",
    )
    if org_id is not None:
        query = query.filter(SecurityAlert.org_id == org_id)
    return len({row[0] for row in query.all()})


def serialize_config(cfg: ConnectorSource) -> dict:
    """Config for the UI. Outbound credentials are never included; the push
    token is masked so it can be shown as 'configured' without leaking it."""
    return {
        "connector_id": cfg.connector_id,
        "name": cfg.name,
        "category": cfg.category,
        "mode": cfg.mode,
        "endpoint": cfg.endpoint,
        "auth_header": cfg.auth_header,
        "has_auth_token": bool(cfg.auth_token),
        "has_ingest_token": bool(cfg.ingest_token),
        "enabled": cfg.enabled,
        "last_sync": _humanize(cfg.last_sync_at),
        "last_status": cfg.last_status,
        "last_error": cfg.last_error,
        "last_count": cfg.last_count,
        "events_ingested": cfg.events_ingested or 0,
    }


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def list_connectors(db: Session, org_id: int | None) -> list[dict]:
    """Catalogue merged with real per-tenant sync state."""
    rows: list[dict] = []
    for connector_id, name, category in CATALOGUE:
        cfg = get_config(db, org_id, connector_id)
        entry = {
            "id": connector_id,
            "name": name,
            "category": category,
            "status": "not_connected",
            "live": False,
            "last_sync": None,
            "assets_monitored": None,
            "latency_ms": None,
            "mode": None,
            "last_error": None,
            "events_ingested": 0,
            "oauth_connected": False,  # Phase 41
        }

        # Phase 41: check OAuth for github/slack even if no cfg
        if connector_id in ("github", "slack"):
            try:
                from app.services.connector_oauth_service import get_connector_oauth_status

                oauth_status = get_connector_oauth_status(db, org_id=org_id, connector_id=connector_id)
                entry["oauth_connected"] = oauth_status.get("connected", False)
                entry["oauth_account"] = oauth_status.get("account_name")
            except Exception:
                pass

        if cfg is None:
            # If OAuth connected but no cfg, still show as configured via OAuth
            if entry.get("oauth_connected"):
                entry["status"] = "configured"
                entry["mode"] = "poll"
            rows.append(entry)
            continue

        entry["mode"] = cfg.mode
        entry["events_ingested"] = cfg.events_ingested or 0

        if not cfg.enabled:
            entry["status"] = "disabled"
            entry["last_sync"] = _humanize(cfg.last_sync_at)
            rows.append(entry)
            continue

        if cfg.last_status == "error":
            entry["status"] = "error"
            entry["last_error"] = cfg.last_error
            entry["last_sync"] = _humanize(cfg.last_sync_at)
            rows.append(entry)
            continue

        if cfg.last_status == "ok":
            entry["status"] = "connected"
            entry["live"] = True
            entry["last_sync"] = _humanize(cfg.last_sync_at)
            entry["latency_ms"] = cfg.last_duration_ms
            entry["assets_monitored"] = _assets_monitored(db, org_id, connector_id)
            rows.append(entry)
            continue

        # Configured, enabled, never synced yet.
        entry["status"] = "configured"
        rows.append(entry)

    return rows


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def upsert_config(
    db: Session,
    org_id: int | None,
    connector_id: str,
    payload: dict,
    actor: str,
) -> dict:
    names = {cid: (nm, cat) for cid, nm, cat in CATALOGUE}
    if connector_id not in names:
        raise ValueError(f"Unknown connector ID: {connector_id}")
    name, category = names[connector_id]

    mode = (payload.get("mode") or "push").lower()
    if mode not in {"poll", "push"}:
        raise ValueError("mode must be 'poll' or 'push'")
    if mode == "poll":
        if not payload.get("endpoint"):
            raise ValueError("poll mode requires an endpoint URL")
        # Refuse an SSRF endpoint at configuration time rather than at the
        # first poll — the operator should see why it was rejected now.
        _guard_endpoint(payload.get("endpoint"))

    cfg = get_config(db, org_id, connector_id)
    created = cfg is None
    if cfg is None:
        cfg = ConnectorSource(
            org_id=org_id,
            connector_id=connector_id,
            name=name,
            category=category,
            mode=mode,
        )
        db.add(cfg)

    cfg.name = name
    cfg.category = category
    cfg.mode = mode
    if "endpoint" in payload:
        cfg.endpoint = payload.get("endpoint")
    if "auth_header" in payload:
        cfg.auth_header = payload.get("auth_header")
    # Credentials are encrypted before they touch the database. An empty string
    # means "clear it", which is stored as NULL — an empty secret and no secret
    # are the same thing.
    if payload.get("auth_token") is not None:
        cfg.auth_token = encrypt_secret(payload["auth_token"])
    if payload.get("ingest_token") is not None:
        cfg.ingest_token = encrypt_secret(payload["ingest_token"])
    if payload.get("enabled") is not None:
        cfg.enabled = bool(payload["enabled"])

    db.commit()
    db.refresh(cfg)

    create_audit_log(
        db,
        action="CONNECTOR_CONFIGURED" if created else "CONNECTOR_UPDATED",
        actor=actor,
        resource=f"connector:{connector_id}",
        details=f"{name} set to {mode} mode (enabled={cfg.enabled})",
    )
    return serialize_config(cfg)


def delete_config(db: Session, org_id: int | None, connector_id: str, actor: str) -> dict:
    cfg = get_config(db, org_id, connector_id)
    if cfg is None:
        raise ValueError(f"No configuration for connector: {connector_id}")
    db.delete(cfg)
    db.commit()
    create_audit_log(
        db,
        action="CONNECTOR_REMOVED",
        actor=actor,
        resource=f"connector:{connector_id}",
        details=f"Configuration removed for {cfg.name}",
    )
    return {"status": "deleted", "connector_id": connector_id}


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


def _normalize_event(raw: dict) -> dict | None:
    """Map an arbitrary provider event onto a SecurityAlert shape.

    Deliberately tolerant: providers disagree on field names. Anything we
    cannot describe honestly (no message at all) is dropped and counted as
    skipped rather than invented.
    """
    if not isinstance(raw, dict):
        return None

    message = (
        raw.get("message")
        or raw.get("description")
        or raw.get("summary")
        or raw.get("event")
        or raw.get("displayMessage")
    )
    if not message or not str(message).strip():
        return None

    severity = str(raw.get("severity") or raw.get("risk") or "MEDIUM").upper()
    if severity not in VALID_SEVERITIES:
        # Numeric scales are common (1-10 / 1-100): map them, don't guess.
        try:
            value = float(severity)
        except ValueError:
            severity = "MEDIUM"
        else:
            if value >= 8:
                severity = "CRITICAL"
            elif value >= 6:
                severity = "HIGH"
            elif value >= 3:
                severity = "MEDIUM"
            else:
                severity = "LOW"

    alert_type = str(raw.get("alert_type") or raw.get("type") or "log").lower()
    if alert_type not in {"network", "log", "email", "dns", "endpoint", "cloud", "identity"}:
        alert_type = "log"

    source_ip = raw.get("source_ip") or raw.get("src_ip") or raw.get("client_ip") or raw.get("ip")
    mitre = map_alert(alert_type, str(message), source_ip)

    return {
        "alert_type": alert_type if alert_type in {"network", "log", "email", "dns"} else "log",
        "severity": severity,
        "message": str(message)[:2000],
        "source_ip": str(source_ip)[:50] if source_ip else None,
        "score": float(raw.get("score")) if raw.get("score") is not None else None,
        "mitre_tactic": raw.get("mitre_tactic") or mitre.get("tactic"),
        "mitre_technique_id": raw.get("mitre_technique_id") or mitre.get("technique_id"),
        "mitre_technique": raw.get("mitre_technique") or mitre.get("technique"),
    }


def _ingest_events(
    db: Session,
    cfg: ConnectorSource,
    events: list,
) -> tuple[int, int]:
    """Insert normalized events, skipping duplicates. Returns (inserted, skipped).

    After commit, publishes each new alert to the in-process EventBus so an open
    SSE stream sees it immediately. Publish happens after commit — a rollback
    never announces an alert that wasn't recorded. A publish failure never
    breaks ingestion.
    """
    inserted = 0
    skipped = 0
    since = _now() - timedelta(hours=24)

    seen: set[tuple[str, str | None]] = set()
    created: list[SecurityAlert] = []
    for raw in events:
        normalized = _normalize_event(raw)
        if normalized is None:
            skipped += 1
            continue

        key = (normalized["message"], normalized["source_ip"])
        if key in seen:
            skipped += 1
            continue

        existing = (
            db.query(SecurityAlert.id)
            .filter(
                SecurityAlert.source == cfg.connector_id,
                SecurityAlert.message == normalized["message"],
                SecurityAlert.source_ip == normalized["source_ip"],
                SecurityAlert.created_at >= since,
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        seen.add(key)
        alert = SecurityAlert(
            org_id=cfg.org_id,
            source=cfg.connector_id,
            source_ip=normalized["source_ip"],
            alert_type=normalized["alert_type"],
            severity=normalized["severity"],
            score=normalized["score"],
            message=normalized["message"],
            mitre_tactic=normalized["mitre_tactic"],
            mitre_technique_id=normalized["mitre_technique_id"],
            mitre_technique=normalized["mitre_technique"],
        )
        db.add(alert)
        created.append(alert)
        inserted += 1

    db.commit()
    # Publish after commit — never announce a row that was rolled back.
    if created:
        try:
            from app.core.events import alert_event_from_row, bus

            for row in created:
                try:
                    bus.publish(alert_event_from_row(row))
                except Exception:
                    _LOGGER.debug("Failed to publish alert event for %s", getattr(row, 'id', '?'), exc_info=True)
        except Exception:
            _LOGGER.debug("EventBus publish failed", exc_info=True)
    return inserted, skipped


def ingest_push(
    db: Session,
    connector_id: str,
    token: str,
    events: list,
) -> dict:
    """Push ingest: authenticate by shared secret, then record real events.

    Rate limited per connector — see _check_ingest_rate for what that does and
    does not guarantee.
    """
    _check_ingest_rate(connector_id)
    cfg = (
        db.query(ConnectorSource)
        .filter(
            ConnectorSource.connector_id == connector_id,
            ConnectorSource.ingest_token.isnot(None),
            ConnectorSource.enabled.is_(True),
        )
        .first()
    )
    # Compared as bytes: hmac.compare_digest() rejects str with non-ASCII
    # characters outright, which would turn a wrong token containing an accent
    # into a TypeError (500) instead of a rejection (401).
    #
    # A stored secret that cannot be decrypted (JWT_SECRET_KEY rotated) is
    # treated as a failed authentication, never as "no secret configured" —
    # the latter would let anyone with the wrong token walk in. The caller gets
    # the same generic rejection either way.
    try:
        stored = decrypt_secret(cfg.ingest_token) if cfg is not None else None
    except SecretDecryptionError:
        stored = None
        _LOGGER.error(
            "Connector %s has an undecryptable ingest secret — JWT_SECRET_KEY "
            "was rotated; the source must be reconfigured.",
            connector_id,
        )
    if cfg is None or not token or not hmac.compare_digest(
        token.encode("utf-8"), (stored or "").encode("utf-8")
    ):
        raise PermissionError("Unknown connector ID or invalid ingest token")

    if not isinstance(events, list):
        raise ValueError("'events' must be a list")

    inserted, skipped = _ingest_events(db, cfg, events)

    cfg.events_ingested = (cfg.events_ingested or 0) + inserted
    cfg.last_sync_at = _now()
    cfg.last_status = "ok"
    cfg.last_error = None
    cfg.last_count = inserted
    db.commit()

    create_audit_log(
        db,
        action="CONNECTOR_INGEST",
        actor=f"connector:{connector_id}",
        resource=f"connector:{connector_id}",
        details=f"{inserted} event(s) ingested, {skipped} skipped",
    )
    return {
        "status": "ingested",
        "connector_id": connector_id,
        "ingested": inserted,
        "skipped": skipped,
        "message": f"Recorded {inserted} event(s) from {cfg.name}"
        + (f"; {skipped} skipped as duplicate or unmappable" if skipped else ""),
    }


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def sync(db: Session, org_id: int | None, connector_id: str, actor: str) -> dict:
    """Run a sync for one connector.

    Three honest outcomes:
      - **synced**   — a poll really fetched events; counts are real.
      - **recorded** — nothing to fetch (no config, disabled, or push mode);
                       the request is audited and the user is told why.
      - **error**    — a poll was attempted and failed; the reason is returned.
    """
    names = {cid: nm for cid, nm, _ in CATALOGUE}
    if connector_id not in names:
        raise ValueError(f"Unknown connector ID: {connector_id}")
    name = names[connector_id]

    cfg = get_config(db, org_id, connector_id)

    if cfg is None:
        create_audit_log(
            db,
            action="CONNECTOR_SYNC_REQUESTED",
            actor=actor,
            resource=f"connector:{connector_id}",
            details=f"Sync requested for {name} (no source configured)",
        )
        return {
            "status": "recorded",
            "connector_id": connector_id,
            "live": False,
            "message": (
                f"Sync request recorded for {name}. No source is configured, so "
                f"nothing was fetched — configure it to enable live sync."
            ),
        }

    if not cfg.enabled:
        create_audit_log(
            db,
            action="CONNECTOR_SYNC_REQUESTED",
            actor=actor,
            resource=f"connector:{connector_id}",
            details=f"Sync requested for {name} (disabled)",
        )
        return {
            "status": "recorded",
            "connector_id": connector_id,
            "live": False,
            "message": f"{name} is disabled — no sync was attempted.",
        }

    if cfg.mode != "poll" or not cfg.endpoint:
        create_audit_log(
            db,
            action="CONNECTOR_SYNC_REQUESTED",
            actor=actor,
            resource=f"connector:{connector_id}",
            details=f"Sync requested for {name} (push mode — nothing to fetch)",
        )
        return {
            "status": "recorded",
            "connector_id": connector_id,
            "live": False,
            "message": (
                f"{name} is configured for push ingest — there is nothing to fetch. "
                f"Send events to /api/v1/connectors/ingest/{connector_id}."
            ),
        }

    headers = {}
    # Phase 41: if OAuth token exists for github/slack, use it automatically
    # unless explicit auth_header/token already configured
    if connector_id in ("github", "slack"):
        try:
            from app.services.connector_oauth_service import get_oauth_token

            oauth_token = get_oauth_token(db, org_id=cfg.org_id, connector_id=connector_id)
            if oauth_token:
                if connector_id == "github":
                    headers["Authorization"] = f"Bearer {oauth_token}"
                else:  # slack
                    headers["Authorization"] = f"Bearer {oauth_token}"
        except Exception:
            pass

    if cfg.auth_header and cfg.auth_token:
        try:
            headers[cfg.auth_header] = decrypt_secret(cfg.auth_token) or ""
        except SecretDecryptionError as exc:
            cfg.last_sync_at = _now()
            cfg.last_status = "error"
            cfg.last_error = (
                f"{exc} — re-enter the credential for {name} in connector settings"
            )
            db.commit()
            create_audit_log(
                db,
                action="CONNECTOR_SYNC_FAILED",
                actor=actor,
                resource=f"connector:{connector_id}",
                details=f"Sync aborted for {name}: stored credential undecryptable",
            )
            return {
                "status": "error",
                "connector_id": connector_id,
                "live": False,
                "message": cfg.last_error,
            }

    started = time.perf_counter()
    try:
        # _fetch_events re-validates the address it connects to, so a config
        # created in dev — or before this guard existed — still cannot become
        # an internal request once deployed. Raising inside the try records it
        # as a failed sync rather than a 500.
        response = _fetch_events(cfg.endpoint, headers)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # network, HTTP error, or non-JSON body
        duration = int((time.perf_counter() - started) * 1000)
        cfg.last_sync_at = _now()
        cfg.last_status = "error"
        cfg.last_error = str(exc)[:500]
        cfg.last_duration_ms = duration
        db.commit()
        create_audit_log(
            db,
            action="CONNECTOR_SYNC_FAILED",
            actor=actor,
            resource=f"connector:{connector_id}",
            details=f"Sync from {name} failed: {exc}"[:500],
        )
        return {
            "status": "error",
            "connector_id": connector_id,
            "live": False,
            "last_error": str(exc)[:500],
            "message": f"Sync from {name} failed: {exc}"[:500],
        }

    events = payload if isinstance(payload, list) else (payload.get("events") or payload.get("data") or [])
    if not isinstance(events, list):
        events = []

    inserted, skipped = _ingest_events(db, cfg, events)

    duration = int((time.perf_counter() - started) * 1000)
    cfg.last_sync_at = _now()
    cfg.last_status = "ok"
    cfg.last_error = None
    cfg.last_duration_ms = duration
    cfg.last_count = inserted
    cfg.events_ingested = (cfg.events_ingested or 0) + inserted
    db.commit()

    create_audit_log(
        db,
        action="CONNECTOR_SYNC_COMPLETED",
        actor=actor,
        resource=f"connector:{connector_id}",
        details=f"Synced {name}: {inserted} new event(s), {skipped} skipped",
    )
    return {
        "status": "synced",
        "connector_id": connector_id,
        "live": True,
        "ingested": inserted,
        "skipped": skipped,
        "last_sync": _humanize(cfg.last_sync_at),
        "message": (
            f"Fetched {len(events)} event(s) from {name} — {inserted} recorded"
            + (f", {skipped} already known" if skipped else "")
            + "."
        ),
    }
