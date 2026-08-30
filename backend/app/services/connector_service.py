"""Real connector ingest - configuration, polling and push, with honest status.

Replaces the hardcoded connector list. The rules this module exists to uphold:

1. **A connector is "connected" only if it is configured, enabled, and its
   last sync succeeded.** Otherwise it says so (`configured` / `not_connected`).
2. **Every number is derived from rows this deployment actually ingested.**
   `assets_monitored` counts distinct source IPs seen from that connector;
   `latency_ms` is the measured duration of the last request.
3. **Failures are reported, never swallowed.** A failed poll returns
   `status: "error"` with the exception text and records it on the row - it
   does not fall back to a cheerful "success".
"""

from __future__ import annotations

import hmac
import ipaddress
import secrets
import logging
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
import app.core.secrets as _secrets_mod
from app.core.secrets import SecretDecryptionError as _SecretDecryptionError, decrypt_secret as _decrypt_secret, encrypt_secret as _encrypt_secret
from app.models import ConnectorSource, SecurityAlert
from app.services.mitre import map_alert
import json
from app.utils.helpers import create_audit_log

# Compatibility wrappers that always use current module's class/function (handles importlib.reload in tests)
def _current_decrypt_secret(*args, **kwargs):
    return _secrets_mod.decrypt_secret(*args, **kwargs)

def _current_encrypt_secret(*args, **kwargs):
    return _secrets_mod.encrypt_secret(*args, **kwargs)

def _current_secret_error():
    return _secrets_mod.SecretDecryptionError

# For backward compat, keep names but resolve dynamically
def decrypt_secret(stored):
    return _secrets_mod.decrypt_secret(stored)

def encrypt_secret(value):
    return _secrets_mod.encrypt_secret(value)

SecretDecryptionError = _secrets_mod.SecretDecryptionError

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ingest rate limiting
# ---------------------------------------------------------------------------
#
# The push webhook is unauthenticated apart from the shared secret, so
# "anyone holding the token can post" also means "as fast as they like" -
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


# The catalogue - the sources NOCTRA is built to ingest from. A catalogue entry
# alone proves nothing; it only becomes "connected" once a source row exists and
# has synced successfully.
# Phase 40: expanded from 4 to 10 - more telemetry makes the live stream busy
# and the scheduled poller useful. Each entry is a real product with a real API.
CATALOGUE: list[tuple[str, str, str]] = [
    ("okta", "Okta Identity Cloud", "Identity"),
    ("sentinel", "CrowdStrike / Sentinel EDR", "Endpoint"),
    ("guardduty", "AWS GuardDuty & IAM Audit", "Cloud Security"),
    ("cloudflare", "Cloudflare Edge WAF", "Network & Edge"),
    # Phase 40 - breadth: code, collaboration, productivity, identity, observability, SIEM
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
# environments refuse internal addresses - see _guard_endpoint.
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
    (http://127.0.0.1) depends on that - while a deployed instance must refuse
    exactly that address. k8s/configmap.yaml sets ENVIRONMENT="production".

    Two honest limits:
    * A name this process cannot resolve cannot be judged here, so it is
      allowed through and left to fail (or succeed) at request time.
    * DNS rebinding between this check and requests' own lookup is not
      covered - closing that means pinning the resolved IP for the
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
    "endpoint resolves to a private, loopback or link-local address - "
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
    ``tls_hostname`` is None when nothing was pinned - either the host is
    already an IP literal, or the name does not resolve (in which case the
    request fails with its own error rather than one we invented).

    ``addresses`` is what the caller must validate: they are the addresses the
    request will actually use. Checking a *different* resolution - which is
    what calling getaddrinfo twice does - leaves the rebinding window wide
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
        return url, {}, None, [host]  # IP literal - nothing to rebind

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
# Webhook HMAC verification (Phase 42)
# ---------------------------------------------------------------------------


def verify_github_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Verify GitHub webhook HMAC SHA256 signature.

    GitHub sends X-Hub-Signature-256: sha256=<hex digest of HMAC-SHA256(raw_body, secret)>
    """
    if not signature_header or not secret:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, "sha256").hexdigest()
    received = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, received)


def verify_slack_signature(
    raw_body: bytes, timestamp_header: str | None, signature_header: str | None, signing_secret: str
) -> bool:
    """Verify Slack webhook signature.

    Slack: basestring = v0:{timestamp}:{raw_body}
           signature = v0=<hex HMAC-SHA256(basestring, signing_secret)>
    Timestamp must be within 5 minutes to prevent replay.
    """
    if not timestamp_header or not signature_header or not signing_secret:
        return False
    try:
        ts = int(timestamp_header)
    except ValueError:
        return False
    now = int(time.time())
    if abs(now - ts) > 300:
        return False
    basestring = f"v0:{timestamp_header}:{raw_body.decode('utf-8', errors='replace')}"
    expected = "v0=" + hmac.new(signing_secret.encode("utf-8"), basestring.encode("utf-8"), "sha256").hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ---------------------------------------------------------------------------
# Real connector fetch - GitHub Advanced Security + Slack Audit Logs (Phase 42)
# ---------------------------------------------------------------------------


# Field names each provider uses for "when this actually happened". Checked in
# order; the first that parses wins.
_EVENT_TIME_FIELDS = (
    "event_time",          # our own normalized shape / generic webhooks
    "date_create",         # Slack audit logs (epoch seconds)
    "activityDateTime",    # Microsoft Graph auditLogs
    "createdDateTime",     # Microsoft Graph signIns
    "created_at",          # GitHub
    "updated_at",          # GitHub (fallback when created_at is absent)
    "timestamp",           # generic
    "time",                # generic
    "@timestamp",          # Elastic-style
    "eventTime",           # generic camelCase
)

# Anything outside this band is a parsing artefact, not a real event time:
# epoch 0, a year-9999 sentinel, or seconds misread as milliseconds. Accepting
# them would produce absurd detection latencies that look like real outliers.
_MIN_EVENT_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)
_FUTURE_TOLERANCE = timedelta(hours=24)


def _resolve_zone(name: str | None):
    """An IANA zone name, or None when unset/unknown.

    An unrecognised name falls back to UTC rather than raising: a typo in
    configuration must not stop ingestion, and the alert is still worth more
    than the hour it may be out by.
    """
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(str(name).strip())
    except Exception:
        _LOGGER.warning("Unknown event_time_zone %r; treating naive times as UTC", name)
        return None


def _coerce_event_time(value, tz=None) -> datetime | None:
    """Best-effort parse of a provider timestamp into aware UTC.

    Returns None rather than a guess. A wrong event time is worse than a
    missing one: detection latency is computed from this field, so a bad value
    silently corrupts the metric instead of being reported as unmeasured.

    ``tz`` is the source's declared zone, applied *only* to timestamps that
    carry no offset. A value that states its own offset is always believed;
    the setting exists for sources that emit bare local time, which cannot be
    distinguished from UTC by inspection.
    """
    if value is None or isinstance(value, bool):
        return None

    parsed: datetime | None = None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        # Epoch values are absolute by definition; the zone never applies.
        parsed = _epoch_to_datetime(float(value))
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Numeric string: epoch seconds (Slack) or milliseconds.
        try:
            parsed = _epoch_to_datetime(float(text))
        except ValueError:
            # ISO 8601. Python < 3.11 rejects the trailing "Z".
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        # No offset in the payload. Use the source's declared zone if it has
        # one, else UTC — never the host's local time, which would make the
        # figures depend on where the server happens to run.
        parsed = parsed.replace(tzinfo=tz or timezone.utc)
    # Always normalise to UTC before returning. The column is naive, so a value
    # left at a local offset would have its tzinfo dropped on write and be
    # stored as local time wearing a UTC label.
    parsed = parsed.astimezone(timezone.utc)

    if parsed < _MIN_EVENT_TIME:
        return None
    if parsed > datetime.now(timezone.utc) + _FUTURE_TOLERANCE:
        return None
    return parsed


def _epoch_to_datetime(number: float) -> datetime | None:
    """Interpret a number as epoch seconds, or milliseconds when too large."""
    if number <= 0:
        return None
    # ~2001-09-09 in seconds; anything above is milliseconds.
    if number > 1_000_000_000_000:
        number = number / 1000.0
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _extract_event_time(raw: dict, tz=None) -> datetime | None:
    """Pull the source event time out of a provider payload."""
    if not isinstance(raw, dict):
        return None
    for field in _EVENT_TIME_FIELDS:
        if field in raw:
            parsed = _coerce_event_time(raw.get(field), tz)
            if parsed is not None:
                return parsed
    # Microsoft Graph nests the sign-in time one level down in some shapes.
    for container in ("status", "activity", "details"):
        nested = raw.get(container)
        if isinstance(nested, dict):
            for field in _EVENT_TIME_FIELDS:
                if field in nested:
                    parsed = _coerce_event_time(nested.get(field), tz)
                    if parsed is not None:
                        return parsed
    return None


def _parse_link_header(link: str) -> dict:
    """Parse GitHub Link header for pagination: <url>; rel="next", ..."""
    links = {}
    if not link:
        return links
    for part in link.split(","):
        part = part.strip()
        if ";" not in part:
            continue
        url_part, rel_part = part.split(";", 1)
        url = url_part.strip()[1:-1]
        rel = None
        for param in rel_part.split(";"):
            param = param.strip()
            if param.startswith("rel="):
                rel = param[4:].strip('"')
        if rel:
            links[rel] = url
    return links


def _normalize_github_alert(raw: dict, alert_type: str = "code_scanning", tz=None) -> dict | None:
    """Map GitHub Advanced Security alert to our normalized event shape."""
    if not isinstance(raw, dict):
        return None
    rule = raw.get("rule", {}) if isinstance(raw.get("rule"), dict) else {}
    message = (
        rule.get("description")
        or raw.get("description")
        or raw.get("secret_type_display_name")
        or raw.get("message")
        or f"GitHub {alert_type} alert: {raw.get('html_url', raw.get('url', ''))}"
    )
    if not message:
        return None
    gh_sev = str(raw.get("severity") or rule.get("severity") or "medium").lower()
    severity_map = {
        "critical": "CRITICAL",
        "high": "HIGH",
        "error": "HIGH",
        "medium": "MEDIUM",
        "moderate": "MEDIUM",
        "warning": "MEDIUM",
        "low": "LOW",
        "note": "LOW",
    }
    severity = severity_map.get(gh_sev, "MEDIUM")
    repo = raw.get("repository", {}) if isinstance(raw.get("repository"), dict) else {}
    repo_name = repo.get("full_name") or raw.get("repository_full_name") or ""
    return {
        "message": f"{message} [{repo_name}]" if repo_name else str(message)[:2000],
        "severity": severity,
        "alert_type": "log",
        "source_ip": None,
        "score": None,
        "mitre_tactic": None,
        "mitre_technique_id": None,
        "mitre_technique": None,
        "event_time": _extract_event_time(raw, tz),
        "github_alert_type": alert_type,
        "github_url": raw.get("html_url") or raw.get("url"),
    }


def _normalize_slack_audit_event(raw: dict, tz=None) -> dict | None:
    """Map Slack Audit Logs event to normalized shape."""
    if not isinstance(raw, dict):
        return None
    action = raw.get("action") or raw.get("type") or "audit"
    actor = raw.get("actor", {}) if isinstance(raw.get("actor"), dict) else {}
    actor_email = ""
    if isinstance(actor.get("user"), dict):
        actor_email = actor.get("user", {}).get("email", "")
    else:
        actor_email = actor.get("email", "")
    message = f"Slack audit: {action} by {actor_email or actor.get('user_id', 'unknown')}"
    details = raw.get("details") or raw.get("context") or ""
    if details and isinstance(details, dict):
        message += f" - {str(details)[:500]}"
    elif details:
        message += f" - {str(details)[:500]}"
    sev = "MEDIUM"
    high_actions = {"user_login_failed", "app_approved", "role_change", "member_joined_via_group", "permissions_added"}
    if action in high_actions or "failed" in action or "admin" in action:
        sev = "HIGH"
    return {
        "message": str(message)[:2000],
        "severity": sev,
        "alert_type": "log",
        "source_ip": raw.get("ip_address") or raw.get("ip") or (raw.get("actor", {}).get("ip_address") if isinstance(raw.get("actor"), dict) else None),
        "score": None,
        "mitre_tactic": None,
        "mitre_technique_id": None,
        "mitre_technique": None,
        "event_time": _extract_event_time(raw, tz),
        "slack_action": action,
    }


def _fetch_github_events(
    oauth_token: str,
    since: str | None = None,
    cursor: str | None = None,
    max_pages: int = 3,
    tz=None,
) -> tuple[list[dict], str | None, dict]:
    """Fetch GitHub Advanced Security alerts using OAuth token."""
    headers = {
        "Authorization": f"Bearer {oauth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    events: list[dict] = []
    next_cursor = None
    state: dict = {}
    orgs = []
    try:
        orgs_resp = _fetch_events("https://api.github.com/user/orgs", headers)
        if orgs_resp.status_code == 200:
            orgs_data = orgs_resp.json()
            if isinstance(orgs_data, list):
                orgs = [o.get("login") for o in orgs_data if isinstance(o, dict) and o.get("login")]
    except Exception as exc:
        _LOGGER.debug("Failed to fetch GitHub orgs: %s", exc)
    targets = orgs[:5]
    if not targets:
        try:
            user_resp = _fetch_events("https://api.github.com/user", headers)
            if user_resp.status_code == 200:
                login = user_resp.json().get("login")
                if login:
                    targets = [login]
        except Exception:
            pass
    alert_types = ["code-scanning", "secret-scanning", "dependabot"]
    for org in targets:
        for atype in alert_types:
            url = f"https://api.github.com/orgs/{org}/{atype}/alerts?per_page=20&state=open"
            if since:
                url += f"&since={since}"
            if cursor and atype == "code-scanning" and cursor.isdigit():
                url += f"&page={cursor}"
            try:
                for _ in range(max_pages):
                    resp = _fetch_events(url, headers)
                    if resp.status_code == 403 and "rate limit" in resp.text.lower():
                        _LOGGER.warning("GitHub rate limited for %s %s", org, atype)
                        break
                    resp.raise_for_status()
                    data = resp.json()
                    if not isinstance(data, list):
                        break
                    for item in data:
                        norm = _normalize_github_alert(item, atype, tz)
                        if norm:
                            events.append(norm)
                    link_header = resp.headers.get("Link", "") if hasattr(resp, "headers") else ""
                    links = _parse_link_header(link_header)
                    next_url = links.get("next")
                    if not next_url or len(events) >= 100:
                        break
                    url = next_url
                if len(events) >= 100:
                    break
            except Exception as exc:
                _LOGGER.debug("GitHub fetch failed for %s %s: %s", org, atype, exc)
                continue
        if len(events) >= 100:
            break
    if len(events) >= 100:
        next_cursor = "2"
    state = {"orgs_fetched": len(targets), "alert_types": alert_types, "since": since}
    return events, next_cursor, state


def _fetch_slack_audit_events(
    oauth_token: str,
    cursor: str | None = None,
    max_pages: int = 3,
    tz=None,
) -> tuple[list[dict], str | None, dict]:
    """Fetch Slack Audit Logs using OAuth token with cursor pagination."""
    headers = {"Authorization": f"Bearer {oauth_token}"}
    events: list[dict] = []
    next_cursor = cursor
    state: dict = {}
    url = "https://api.slack.com/audit/v1/logs?limit=50"
    if cursor:
        url += f"&cursor={cursor}"
    for _ in range(max_pages):
        try:
            resp = _fetch_events(url, headers)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After", "60") if hasattr(resp, "headers") else "60"
                _LOGGER.warning("Slack audit logs rate limited, Retry-After %s", retry_after)
                break
            resp.raise_for_status()
            data = resp.json()
            entries = data.get("entries") if isinstance(data, dict) else data
            if not isinstance(entries, list):
                break
            for entry in entries:
                norm = _normalize_slack_audit_event(entry, tz)
                if norm:
                    events.append(norm)
            if isinstance(data, dict):
                rm = data.get("response_metadata", {}) or {}
                nc = rm.get("next_cursor")
                if nc:
                    next_cursor = nc
                    url = f"https://api.slack.com/audit/v1/logs?limit=50&cursor={nc}"
                    if len(events) >= 100:
                        break
                    continue
            break
        except Exception as exc:
            _LOGGER.debug("Slack audit fetch failed: %s", exc)
            break
    state = {"pages_fetched": max_pages, "cursor": next_cursor}
    return events, next_cursor, state

def _normalize_gworkspace_event(raw: dict, tz=None) -> dict | None:
    if not isinstance(raw, dict):
        return None
    # Google Workspace Reports API activity
    actor = raw.get("actor", {}) if isinstance(raw.get("actor"), dict) else {}
    actor_email = actor.get("email") or raw.get("actorEmail") or "unknown"
    events = raw.get("events", []) if isinstance(raw.get("events"), list) else []
    action = ""
    if events and isinstance(events[0], dict):
        action = events[0].get("name") or events[0].get("type") or "activity"
        # Try to get details
        params = events[0].get("parameters", [])
        if params:
            action += " " + " ".join([str(p.get("value", ""))[:100] for p in params[:2] if isinstance(p, dict)])
    else:
        action = raw.get("type") or raw.get("eventType") or "workspace activity"
    message = f"Google Workspace: {action} by {actor_email}"
    ip = raw.get("ipAddress") or actor.get("profileId") or None
    # Infer severity
    sev = "MEDIUM"
    if "login_failure" in action or "suspended" in action or "admin" in action.lower():
        sev = "HIGH"
    return {
        "message": str(message)[:2000],
        "severity": sev,
        "alert_type": "log",
        "source_ip": ip,
        "score": None,
        "mitre_tactic": None,
        "mitre_technique_id": None,
        "mitre_technique": None,
        "event_time": _extract_event_time(raw, tz),
        "gworkspace_action": action,
    }


def _normalize_azuread_event(raw: dict, tz=None) -> dict | None:
    if not isinstance(raw, dict):
        return None
    # Microsoft Graph signIns or auditLogs
    user = raw.get("userPrincipalName") or raw.get("userDisplayName") or raw.get("userId") or "unknown"
    action = raw.get("activityDisplayName") or raw.get("activity") or raw.get("operationName") or "AzureAD activity"
    result = raw.get("result") or raw.get("status", {}).get("errorCode") if isinstance(raw.get("status"), dict) else raw.get("result")
    message = f"AzureAD: {action} by {user}"
    if result and str(result) not in ("0", "success", "Success"):
        message += f" failed: {result}"
    ip = raw.get("ipAddress") or raw.get("clientIp") or (raw.get("location", {}).get("ipAddress") if isinstance(raw.get("location"), dict) else None)
    sev = "MEDIUM"
    if "failed" in message.lower() or "risk" in action.lower() or result not in (None, "0", 0, "success", "Success"):
        sev = "HIGH"
    return {
        "message": str(message)[:2000],
        "severity": sev,
        "alert_type": "log",
        "source_ip": ip,
        "score": None,
        "mitre_tactic": None,
        "mitre_technique_id": None,
        "mitre_technique": None,
        "event_time": _extract_event_time(raw, tz),
        "azuread_action": action,
    }


def _fetch_gworkspace_events(
    oauth_token: str,
    cursor: str | None = None,
    max_pages: int = 3,
    tz=None,
) -> tuple[list[dict], str | None, dict]:
    headers = {"Authorization": f"Bearer {oauth_token}"}
    events: list[dict] = []
    next_cursor = cursor
    state: dict = {}
    # Google Reports API: login activities
    url = "https://admin.googleapis.com/admin/reports/v1/activity/users/all/applications/login?maxResults=50"
    if cursor:
        url += f"&pageToken={cursor}"
    for _ in range(max_pages):
        try:
            resp = _fetch_events(url, headers)
            if resp.status_code == 429:
                break
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items") if isinstance(data, dict) else data
            if not isinstance(items, list):
                break
            for item in items:
                norm = _normalize_gworkspace_event(item, tz)
                if norm:
                    events.append(norm)
            nc = data.get("nextPageToken") if isinstance(data, dict) else None
            if nc:
                next_cursor = nc
                url = f"https://admin.googleapis.com/admin/reports/v1/activity/users/all/applications/login?maxResults=50&pageToken={nc}"
                if len(events) >= 100:
                    break
                continue
            break
        except Exception as exc:
            _LOGGER.debug("Google Workspace fetch failed: %s", exc)
            break
    state = {"pages_fetched": max_pages, "cursor": next_cursor}
    return events, next_cursor, state


def _fetch_azuread_events(
    oauth_token: str,
    cursor: str | None = None,
    max_pages: int = 3,
    tz=None,
) -> tuple[list[dict], str | None, dict]:
    headers = {"Authorization": f"Bearer {oauth_token}"}
    events: list[dict] = []
    next_cursor = cursor
    state: dict = {}
    url = "https://graph.microsoft.com/v1.0/auditLogs/signIns?$top=50"
    if cursor:
        # Azure uses $skiptoken
        url += f"&$skiptoken={cursor}"
    for _ in range(max_pages):
        try:
            resp = _fetch_events(url, headers)
            if resp.status_code == 429:
                break
            resp.raise_for_status()
            data = resp.json()
            items = data.get("value") if isinstance(data, dict) else data
            if not isinstance(items, list):
                break
            for item in items:
                norm = _normalize_azuread_event(item, tz)
                if norm:
                    events.append(norm)
            # Pagination via @odata.nextLink
            next_link = data.get("@odata.nextLink") if isinstance(data, dict) else None
            if next_link:
                # Extract skiptoken if present
                if "$skiptoken=" in next_link:
                    next_cursor = next_link.split("$skiptoken=")[-1].split("&")[0]
                else:
                    next_cursor = next_link
                url = next_link
                if len(events) >= 100:
                    break
                continue
            break
        except Exception as exc:
            _LOGGER.debug("AzureAD fetch failed: %s", exc)
            break
    state = {"pages_fetched": max_pages, "cursor": next_cursor}
    return events, next_cursor, state




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _humanize(moment: datetime | None) -> str | None:
    """'just now' / '4 minutes ago' / '2 days ago' - null in, null out."""
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

    Real telemetry only - no row, no number.
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
        # None means naive timestamps from this source are read as UTC.
        "event_time_zone": cfg.event_time_zone,
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
        # Phase 46: also gworkspace and azuread
        if connector_id in ("github", "slack", "gworkspace", "azuread"):
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
        # first poll - the operator should see why it was rejected now.
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
    # means "clear it", which is stored as NULL - an empty secret and no secret
    # are the same thing.
    if payload.get("auth_token") is not None:
        cfg.auth_token = encrypt_secret(payload["auth_token"])
    if payload.get("ingest_token") is not None:
        cfg.ingest_token = encrypt_secret(payload["ingest_token"])
    if payload.get("enabled") is not None:
        cfg.enabled = bool(payload["enabled"])
    if "event_time_zone" in payload:
        zone = (payload.get("event_time_zone") or "").strip()
        if zone:
            # Reject an unknown zone here rather than silently falling back to
            # UTC at ingest time, where a typo would quietly shift every
            # detection-latency figure from this source.
            try:
                from zoneinfo import ZoneInfo

                ZoneInfo(zone)
            except Exception as exc:
                raise ValueError(
                    f"Unknown time zone {zone!r}. Use an IANA name such as "
                    "'America/New_York'."
                ) from exc
            cfg.event_time_zone = zone
        else:
            cfg.event_time_zone = None

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


def rotate_ingest_secret(db: Session, org_id: int, connector_id: str, *, actor: str) -> dict:
    """Rotate ingest_token for a connector — returns new token once (Phase 46).

    Generates a cryptographically random 32-byte urlsafe secret, stores encrypted,
    logs rotation. Old secret immediately invalid. Returns new secret once.
    """
    cfg = get_config(db, org_id, connector_id)
    if cfg is None:
        raise ValueError(f"No configuration for connector '{connector_id}'")
    new_secret = secrets.token_urlsafe(32)
    cfg.ingest_token = encrypt_secret(new_secret)
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cfg)
    try:
        from app.services.audit_service import log_action

        log_action(
            db,
            action="connector.rotate_secret",
            user_id=0,
            org_id=org_id,
            details={
                "connector_id": connector_id,
                "actor": actor,
                "rotated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        pass
    try:
        create_audit_log(
            db,
            action="CONNECTOR_ROTATE_SECRET",
            actor=actor,
            resource=f"connector:{connector_id}",
            details=f"Rotated ingest secret for {connector_id}",
        )
    except Exception:
        pass
    return {
        "connector_id": connector_id,
        "ingest_token": new_secret,
        "rotated_at": datetime.now(timezone.utc).isoformat(),
        "warning": "Store this token securely — it will not be shown again. Update your webhook source.",
    }


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


def _normalize_event(raw: dict, tz=None) -> dict | None:
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
        "event_time": _extract_event_time(raw, tz),
    }


def _ingest_events(
    db: Session,
    cfg: ConnectorSource,
    events: list,
) -> tuple[int, int]:
    """Insert normalized events, skipping duplicates. Returns (inserted, skipped).

    After commit, publishes each new alert to the in-process EventBus so an open
    SSE stream sees it immediately. Publish happens after commit - a rollback
    never announces an alert that wasn't recorded. A publish failure never
    breaks ingestion.
    """
    inserted = 0
    skipped = 0
    since = _now() - timedelta(hours=24)

    seen: set[tuple[str, str | None]] = set()
    created: list[SecurityAlert] = []
    # Resolved once: parsing hundreds of events should not rebuild the zone.
    source_tz = _resolve_zone(getattr(cfg, "event_time_zone", None))
    for raw in events:
        normalized = _normalize_event(raw, source_tz)
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
            # None when the provider sent nothing parseable. Left NULL rather
            # than defaulted to now(), which would report zero detection
            # latency for sources that never supplied a time at all.
            event_time=normalized.get("event_time"),
        )
        db.add(alert)
        created.append(alert)
        inserted += 1

    db.commit()
    # Publish after commit - never announce a row that was rolled back.
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

        # Phase 49: Threat intel enrichment (best-effort, non-blocking per alert)
        try:
            from app.core.config import settings as _settings
            from app.services import threat_intel_enrichment as _tie

            if getattr(_settings, "THREAT_INTEL_ENABLED", True):
                for row in created:
                    try:
                        # Enrich in same DB session but new transaction per alert to avoid rollback of ingest
                        _tie.enrich_alert_threat_intel(db, row)
                    except Exception as exc:
                        _LOGGER.debug("Threat intel enrich failed for alert %s: %s", getattr(row, "id", "?"), exc)
        except Exception:
            _LOGGER.debug("Threat intel integration outer failed", exc_info=True)

        # Phase 44: auto-triage - create cases for CRITICAL/HIGH alerts from connectors
        try:
            from app.models import Case

            for row in created:
                if (row.severity or "").upper() not in ("CRITICAL", "HIGH"):
                    continue
                try:
                    dup = (
                        db.query(Case)
                        .filter(
                            Case.source_alert_id == row.id,
                            Case.kind == "analyst",
                        )
                        .first()
                    )
                    if dup:
                        continue
                    try:
                        from app.services.ocsf_service import alert_to_ocsf_finding

                        ocsf = alert_to_ocsf_finding(row)
                        desc = f"Auto-triaged from {row.source} connector: {row.message}. OCSF severity {ocsf.get('severity')}."
                    except Exception:
                        desc = f"Auto-triaged from {row.source} connector: {row.message}"

                    case = Case(
                        title=f"[{row.severity}] {row.source} - {row.message[:100]}",
                        description=desc,
                        status="open",
                        priority="critical" if row.severity == "CRITICAL" else "high",
                        source_alert_id=row.id,
                        org_id=row.org_id,
                        kind="analyst",
                        analysis={
                            "what_happened": row.message,
                            "why_it_matters": f"High severity alert from {row.source} requires immediate triage",
                            "blast_radius_summary": f"Source: {row.source}, IP: {row.source_ip or 'N/A'}",
                            # Confidence is computed from real signals once the
                            # case exists (it needs an id to look context up).
                            # A hardcoded 0.85 used to be stamped here, which
                            # told the operator the same thing about every
                            # single auto-triaged alert.
                            "confidence": None,
                            "model": "connector-auto-triage",
                        },
                        proposed_action={
                            "action_type": "ISOLATE_HOST" if row.source_ip else "ALERT_OPERATOR",
                            "target": row.source_ip or row.source,
                            "rationale": f"Auto-triage for {row.severity} alert from {row.source}",
                            "undo": "Re-enable access after investigation",
                        },
                        decision="pending",
                    )
                    db.add(case)
                    db.commit()

                    # Explain the verdict now that the case has an id.
                    from app.services import verdict_reasoning

                    reasoning = verdict_reasoning.explain(db, case)
                    analysis = dict(case.analysis or {})
                    analysis["reasoning"] = reasoning
                    analysis["confidence"] = reasoning.get("confidence")
                    case.analysis = analysis
                    db.commit()

                    _LOGGER.info("Auto-triaged case %s for alert %s from %s", case.id, row.id, row.source)
                except Exception as exc:
                    _LOGGER.debug("Auto-triage failed for alert %s: %s", getattr(row, "id", "?"), exc)
                    try:
                        db.rollback()
                    except Exception:
                        pass
        except Exception as exc:
            _LOGGER.debug("Auto-triage outer failed: %s", exc)

    return inserted, skipped


def ingest_push(
    db: Session,
    connector_id: str,
    token: str,
    events: list,
    raw_body: bytes | None = None,
    github_signature: str | None = None,
    slack_signature: str | None = None,
    slack_timestamp: str | None = None,
) -> dict:
    """Push ingest: authenticate by shared secret or HMAC signature, then record real events.

    Phase 42: supports GitHub X-Hub-Signature-256 and Slack X-Slack-Signature verification.
    If raw_body + signature headers provided, HMAC is verified using ingest_token as webhook secret.
    Falls back to simple token comparison (X-Connector-Token) for backward compat.

    Rate limited per connector - see _check_ingest_rate for what that does and
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
    try:
        stored = _secrets_mod.decrypt_secret(cfg.ingest_token) if cfg is not None else None
    except _secrets_mod.SecretDecryptionError:
        stored = None
        _LOGGER.error(
            "Connector %s has an undecryptable ingest secret - JWT_SECRET_KEY "
            "was rotated; the source must be reconfigured.",
            connector_id,
        )
    except Exception as _exc:
        if "SecretDecryptionError" in type(_exc).__name__ or "cannot be decrypted" in str(_exc) or "not in a recognised format" in str(_exc):
            stored = None
            _LOGGER.error(
                "Connector %s has an undecryptable ingest secret - JWT_SECRET_KEY "
                "was rotated; the source must be reconfigured.",
                connector_id,
            )
        else:
            raise

    authenticated = False
    if cfg is not None and stored:
        if raw_body is not None and github_signature:
            if verify_github_signature(raw_body, github_signature, stored):
                authenticated = True
        if not authenticated and raw_body is not None and slack_signature:
            if verify_slack_signature(raw_body, slack_timestamp, slack_signature, stored):
                authenticated = True
        if not authenticated and token and hmac.compare_digest(
            token.encode("utf-8"), (stored or "").encode("utf-8")
        ):
            authenticated = True
    else:
        if cfg is not None and token and stored:
            if hmac.compare_digest(token.encode("utf-8"), (stored or "").encode("utf-8")):
                authenticated = True

    if not authenticated:
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
      - **synced**   - a poll really fetched events; counts are real.
      - **recorded** - nothing to fetch (no config, disabled, or push mode);
                       the request is audited and the user is told why.
      - **error**    - a poll was attempted and failed; the reason is returned.
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
                f"nothing was fetched - configure it to enable live sync."
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
            "message": f"{name} is disabled - no sync was attempted.",
        }

    if cfg.mode != "poll" or not cfg.endpoint:
        create_audit_log(
            db,
            action="CONNECTOR_SYNC_REQUESTED",
            actor=actor,
            resource=f"connector:{connector_id}",
            details=f"Sync requested for {name} (push mode - nothing to fetch)",
        )
        return {
            "status": "recorded",
            "connector_id": connector_id,
            "live": False,
            "message": (
                f"{name} is configured for push ingest - there is nothing to fetch. "
                f"Send events to /api/v1/connectors/ingest/{connector_id}."
            ),
        }

    headers = {}
    oauth_token = None
    if connector_id in ("github", "slack", "gworkspace", "azuread"):
        try:
            from app.services.connector_oauth_service import get_oauth_token

            oauth_token = get_oauth_token(db, org_id=cfg.org_id, connector_id=connector_id)
            if oauth_token:
                headers["Authorization"] = f"Bearer {oauth_token}"
        except Exception:
            pass

    if cfg.auth_header and cfg.auth_token:
        try:
            headers[cfg.auth_header] = _secrets_mod.decrypt_secret(cfg.auth_token) or ""
        except _secrets_mod.SecretDecryptionError as exc:
            cfg.last_sync_at = _now()
            cfg.last_status = "error"
            cfg.last_error = (
                f"{exc} - re-enter the credential for {name} in connector settings"
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
        except Exception as exc:
            if "SecretDecryptionError" in type(exc).__name__ or "cannot be decrypted" in str(exc) or "not in a recognised format" in str(exc):
                cfg.last_sync_at = _now()
                cfg.last_status = "error"
                cfg.last_error = (
                    f"{exc} - re-enter the credential for {name} in connector settings"
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
            raise

    started = time.perf_counter()
    events: list = []
    next_cursor: str | None = None
    sync_state_data: dict = {}

    is_github_real = connector_id == "github" and oauth_token and cfg.endpoint and "api.github.com" in cfg.endpoint
    is_slack_real = connector_id == "slack" and oauth_token and cfg.endpoint and "slack.com" in cfg.endpoint
    is_gworkspace_real = connector_id == "gworkspace" and oauth_token and cfg.endpoint and "googleapis.com" in cfg.endpoint
    is_azuread_real = connector_id == "azuread" and oauth_token and cfg.endpoint and "graph.microsoft.com" in cfg.endpoint
    if connector_id == "github" and oauth_token and not is_github_real:
        if cfg.endpoint and ("github" in cfg.endpoint.lower() or cfg.endpoint.startswith("https://api.github.com")):
            is_github_real = True
    if connector_id == "slack" and oauth_token and not is_slack_real:
        if cfg.endpoint and ("slack.com" in cfg.endpoint.lower()):
            is_slack_real = True
    if connector_id == "gworkspace" and oauth_token and not is_gworkspace_real:
        if cfg.endpoint and ("googleapis.com" in cfg.endpoint.lower() or "gworkspace" in cfg.endpoint.lower()):
            is_gworkspace_real = True
    if connector_id == "azuread" and oauth_token and not is_azuread_real:
        if cfg.endpoint and ("graph.microsoft.com" in cfg.endpoint.lower() or "azuread" in cfg.endpoint.lower()):
            is_azuread_real = True

    # Declared zone for this source, applied to any timestamp it sends without
    # an offset. Resolved once per sync rather than per event.
    source_tz = _resolve_zone(getattr(cfg, "event_time_zone", None))

    try:
        if is_github_real and oauth_token:
            import json as _json
            since_val = None
            cursor_val = cfg.last_cursor
            if cfg.sync_state:
                try:
                    ss = _json.loads(cfg.sync_state)
                    since_val = ss.get("since")
                except Exception:
                    pass
            events, next_cursor, sync_state_data = _fetch_github_events(
                oauth_token, since=since_val, cursor=cursor_val, tz=source_tz
            )
        elif is_slack_real and oauth_token:
            cursor_val = cfg.last_cursor
            events, next_cursor, sync_state_data = _fetch_slack_audit_events(
                oauth_token, cursor=cursor_val, tz=source_tz
            )
        elif is_gworkspace_real and oauth_token:
            cursor_val = cfg.last_cursor
            events, next_cursor, sync_state_data = _fetch_gworkspace_events(
                oauth_token, cursor=cursor_val, tz=source_tz
            )
        elif is_azuread_real and oauth_token:
            cursor_val = cfg.last_cursor
            events, next_cursor, sync_state_data = _fetch_azuread_events(
                oauth_token, cursor=cursor_val, tz=source_tz
            )
        else:
            response = _fetch_events(cfg.endpoint, headers)
            response.raise_for_status()
            payload = response.json()
            events = payload if isinstance(payload, list) else (payload.get("events") or payload.get("data") or [])
            if not isinstance(events, list):
                events = []
    except Exception as exc:
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

    inserted, skipped = _ingest_events(db, cfg, events)

    duration = int((time.perf_counter() - started) * 1000)
    cfg.last_sync_at = _now()
    cfg.last_status = "ok"
    cfg.last_error = None
    cfg.last_duration_ms = duration
    cfg.last_count = inserted
    cfg.events_ingested = (cfg.events_ingested or 0) + inserted
    if next_cursor:
        cfg.last_cursor = next_cursor
    if sync_state_data:
        import json as _json
        try:
            cfg.sync_state = _json.dumps(sync_state_data)
        except Exception:
            pass
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
            f"Fetched {len(events)} event(s) from {name} - {inserted} recorded"
            + (f", {skipped} already known" if skipped else "")
            + "."
        ),
    }
