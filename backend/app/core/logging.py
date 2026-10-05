"""Structured JSON logging with correlation ids and a PII allowlist (R-54, T-318).

One event per line, JSON outside development, and every line carries the ids that
tie it to the request that produced it: ``request_id`` (T-304's
``X-Request-ID``) and ``trace_id`` (T-317's trace context). A log line without
those is a line nobody can join to the trace it belongs to, which is why they are
bound in middleware rather than passed by every call site.

**R-54 is enforced here, not asked for politely.** The rule says no PII in logs,
usernames and hostnames are redacted or salted-hashed before logging, and
structured log fields are allowlisted. Three processors do exactly that:

* :func:`_redaction_processor` walks the event dict. A key in
  :data:`SECRET_FIELDS` becomes ``[redacted]``. A key in
  :data:`IDENTIFIER_FIELDS` is salted-hashed: a username is an identifier worth
  correlating on, so it keeps its *relationship* (the same value hashes to the
  same name within a deployment) without keeping the value. Any other key that is
  not in :data:`ALLOWED_FIELDS` is **dropped** -- an allowlist that admits
  everything is not an allowlist -- and nested mappings are filtered the same way,
  because ``extra={"user": {...}}`` is a field too.
* Every remaining string, the event name and the formatted exception included,
  goes through :func:`redact_text`, which removes the shapes an identifier takes
  in free text: e-mail addresses, IP addresses, bearer tokens and JWTs, and
  ``user=...``-style assignments. The exception path is the one that matters most
  -- a message like ``no such user: alice@corp`` is exactly the planted username
  R-54 exists to keep out of the log.
* :func:`redact_text` is also the formatter's last step for records that did not
  come from structlog at all (uvicorn's access lines, for instance), since those
  never reach a structlog processor.

**The salt is the deployment's, never a default.** Hashing with a constant key
would be a fake protection -- the hash table of a popular salt is a lookup away --
so the key is derived from ``AEGIS_SECRET_KEY`` under a purpose distinct from the
rate-limit fingerprint's and the api-key digest's (D-042, D-048), and until a
secret is configured an identifier renders as ``[redacted]`` instead of a hash.

**What free-text scrubbing cannot do, and what covers it instead.** A hostname in
prose -- ``the collector at web-01 is down`` -- has no shape to match: any word
could be one, so no pattern decides it. The control for hostnames is the allowlist:
a hostname reaches a log line only by being bound to a field, and a field that is a
``host`` is hashed. The same holds for a username with no ``@`` and no ``user=`` in
front of it. Anything *bound* is redacted by name; anything *quoted* is caught when
it has a shape (an address, a token, an e-mail).

**Field names are the other half of the policy, and they are checked.** A field
*name* can be PII (``alice@corp": 1``), so a dropped key is dropped silently rather
than reported: naming it in a warning would be the leak the drop exists to prevent.
The allowlist is short, written down, and asserted by a test that logs through the
application and checks every key it emits is on the list.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any, cast

import structlog
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Environment, Settings

__all__ = [
    "ALLOWED_FIELDS",
    "IDENTIFIER_FIELDS",
    "REDACTED",
    "SECRET_FIELDS",
    "bind_request_id",
    "bind_trace_id",
    "clear_request_context",
    "configure_logging",
    "get_logger",
    "redact_text",
    "unbind_trace_id",
]

#: What a value that must not be stored is replaced with.
REDACTED = "[redacted]"

#: Prefix on a salted-hashed identifier, so a reader can tell ``id:...`` from a
#: value that happened to survive.
HASH_PREFIX = "id:"

#: Fields a log line may carry. Anything else is dropped by the redaction
#: processor. Every entry is something this application actually records; the list
#: is deliberately small enough to read in one sitting.
ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        # structlog and correlation: which line, from what, for which request.
        "event",
        "level",
        "timestamp",
        "exception",
        "service",
        "request_id",
        "trace_id",
        # The one structured line per request.
        "method",
        "route",
        "status",
        "duration_ms",
        # Audit-shaped facts: what was done, to which internal id, by which hash.
        "action",
        "outcome",
        "target_type",
        "target_id",
        "actor_hash",
        "model_id",
        "model_kind",
        "version",
        "modality",
        "stage",
        "severity",
        "feature",
        "value",
        "count",
        "accepted",
        "rejected",
        "received",
        "alert_id",
        "sequence",
        "entity_id",
        "reason",
        "error_type",
        "detail",
    }
)

#: Fields whose value *is* an identifier and is therefore salted-hashed: the
#: relationship survives, the value does not.
IDENTIFIER_FIELDS: frozenset[str] = frozenset(
    {
        "user",
        "username",
        "actor",
        "subject",
        "email",
        "host",
        "hostname",
        "src_ip",
        "dst_ip",
        "client_ip",
        "address",
        "ip",
        "login",
    }
)

#: Fields that must never be rendered at all, hashed or otherwise.
SECRET_FIELDS: frozenset[str] = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "apikey",
        "key",
        "password",
        "secret",
        "cookie",
        "set-cookie",
        "signature",
    }
)

#: The keyed assignment an identifier takes in free text: ``user=alice``.
_ASSIGNMENT = re.compile(
    r"(?i)\b(user(?:name)?|actor|subject|host(?:name)?|login|email|e-mail)"
    r"(\s*[=:]\s*)([\"']?)([^\s\"',;)]+)\3"
)
#: A local part, an ``@`` and a host: the TLD is optional because an internal
#: login is often ``alice@corp``, which a rule requiring a dot would walk past.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+")
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
#: IPv6 in either form the standard allows: the compressed one needs its ``::``,
#: the expanded one needs all eight groups. A loose "two or more hex groups" rule
#: also matched clock times -- ``10:00:00``, every ISO timestamp -- and mangling the
#: timestamp of a log line is a worse defect than the leak this exists to stop.
_IPV6_COMPRESSED = re.compile(
    r"\b(?:[0-9A-Fa-f]{1,4}:){1,7}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?\b"
)
_IPV6_EXPANDED = re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")

_id_key: bytes | None = None


def _key_for(secret: str) -> bytes:
    """The redaction key for a deployment. Purpose-separated, like every other."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"aegis.logging.redaction.v1",
        info=b"log-identifier",
    ).derive(secret.encode())


def _hash_identifier(value: str) -> str:
    """A stable name for an identifier, or ``[redacted]`` before a key exists."""
    if _id_key is None:
        return REDACTED
    digest = hmac.new(_id_key, value.encode(), hashlib.sha256).hexdigest()
    return f"{HASH_PREFIX}{digest[:12]}"


def redact_text(text: str) -> str:
    """Remove the identifier shapes R-54 forbids from a free-text string.

    Called for the event name, for every string value, and for anything the
    stdlib formatter produces. ``user=alice`` keeps the key and loses the value, so
    a message stays readable and stops naming a person.
    """

    def _assignment(match: re.Match[str]) -> str:
        return f"{match.group(1)}{match.group(2)}{_hash_identifier(match.group(4))}"

    text = _BEARER.sub(REDACTED, text)
    text = _JWT.sub(REDACTED, text)
    text = _EMAIL.sub(lambda match: _hash_identifier(match.group(0)), text)
    text = _IPV4.sub(REDACTED, text)
    text = _IPV6_COMPRESSED.sub(REDACTED, text)
    text = _IPV6_EXPANDED.sub(REDACTED, text)
    return _ASSIGNMENT.sub(_assignment, text)


def _scrub(value: Any) -> Any:
    """Scrub one value, recursing into containers."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return _redact_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_scrub(item) for item in value]
    return value


def _redact_mapping(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the allowlist, the identifier hash and the secret mask to a mapping."""
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if key in SECRET_FIELDS:
            cleaned[key] = REDACTED
        elif key in IDENTIFIER_FIELDS:
            cleaned[key] = _hash_identifier(str(value))
        elif key in ALLOWED_FIELDS:
            cleaned[key] = _scrub(value)
    return cleaned


def _redaction_processor(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """The R-54 processor: allowlist the fields, redact the identifiers."""
    return _redact_mapping(event_dict)


class _ScrubbingFormatter(logging.Formatter):
    """A stdlib formatter that scrubs what it renders.

    Records that never went through structlog -- uvicorn's access line, a
    third-party library's warning -- would otherwise bypass every processor above.
    The scrub is the same one, applied to the finished string.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render the record and redact the result."""
        return redact_text(super().format(record))


def configure_logging(settings: Settings) -> None:
    """Configure structlog and the stdlib root logger for this process.

    Development renders to the console for humans; every other environment emits
    JSON so the output is machine-parseable. Both go through the redaction
    processors: "human-readable" is not a reason to log a username.

    Idempotent by construction (the handlers are replaced rather than added), which
    matters because this runs at every application start -- including the many
    starts inside one test process.
    """
    level = getattr(logging, settings.log_level, logging.INFO)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _redaction_processor,
    ]

    renderer: structlog.typing.Processor
    if settings.env is Environment.DEVELOPMENT:
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        # Not cached: a process that reconfigures (tests, an embedded app) must not
        # keep rendering through the processors of the previous configuration.
        cache_logger_on_first_use=False,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_ScrubbingFormatter("%(message)s"))
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    _set_identifier_key(settings.secret_key)
    bind_service(settings.service_name)


def _set_identifier_key(secret: str) -> None:
    """Derive the deployment's redaction key (module-private, set by configuration)."""
    global _id_key  # noqa: PLW0603
    _id_key = _key_for(secret)


def bind_service(service_name: str) -> None:
    """Bind the service name so every line says which process wrote it."""
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structured logger."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def bind_request_id(request_id: str) -> None:
    """Bind a correlation id that will appear on every subsequent log line."""
    structlog.contextvars.bind_contextvars(request_id=request_id)


def bind_trace_id(trace_id: str) -> None:
    """Bind the trace context id for the request being served (T-317, T-318)."""
    structlog.contextvars.bind_contextvars(trace_id=trace_id)


def unbind_trace_id() -> None:
    """Drop only the trace id, for a layer that bound only that."""
    structlog.contextvars.unbind_contextvars("trace_id")


def clear_request_context() -> None:
    """Drop the per-request ids so a reused task cannot inherit them.

    Only the request-scoped keys are unbound: clearing *all* context would take the
    service name with it, and a log line that has stopped saying which process
    wrote it is a line nobody can place.
    """
    structlog.contextvars.unbind_contextvars("request_id", "trace_id")
