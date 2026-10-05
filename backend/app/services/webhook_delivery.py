"""Signing and delivering alert webhooks, with bounded retries (T-311).

FR-21 sends ``high`` and ``critical`` alerts to an outbound webhook, HMAC-signed,
with retries. Three things here are policy worth stating before the code.

**The signature is over bytes, not over a re-serialisation.** The document is
canonicalised once (sorted keys, compact separators), signed as
``HMAC-SHA256(secret, "<timestamp>.<body>")``, and those exact bytes are what is
sent on every attempt. A receiver that verifies against the body it received is
therefore verifying against the body that was signed; a scheme that signs a
re-serialised object verifies until the day a field order or a float
representation changes.

**Every attempt of one delivery carries the same timestamp and signature.** The
timestamp is what a receiver uses to refuse a replay, and a retry is not a new
event: re-signing per attempt would let a receiver that deduplicates on the
signature treat one alert as several, and re-timestamping would make a delayed
retry indistinguishable from a fresh alert.

**A retry decision is about the receiver's health, not about the alert.** A 5xx,
a timeout or a connection error is worth retrying; a 4xx is not -- the request
was received and refused, so the same bytes will be refused again, and retrying
only delays the operator finding out that their endpoint rejects the payload.
Retries are bounded (five attempts by default, with exponential backoff and full
jitter) and every attempt is logged, because "retries are bounded and logged" is
the acceptance criterion and an unbounded retry loop against a dead endpoint is
how a worker stops delivering anything at all.

**What is logged is deliberately thin.** No URL -- a webhook URL may carry a
token in its path or query -- and no alert content (R-54, R-58). A delivery
record says which target, which attempt, what happened, and the status code. The
operator who needs the payload has the alerts API and the target's own logs.

**The address that was checked is the address that is dialled.** A URL is
validated each time it is about to be used, not only when it was registered: a
hostname that resolved to a public address this morning may resolve to
``169.254.169.254`` this afternoon, and a target registered months ago is exactly
the kind of thing a rebinding attack waits for. The sender hands the transport a
:class:`WebhookRequest`, which names the pinned address to connect to and the
hostname to present for ``Host`` and the TLS SNI -- the transport is never asked
to resolve anything itself.

**What is not here.** The HTTP client. :class:`WebhookTransport` is the
injection point, and the shipped implementation is not written for the same
reason the Kafka producer's broker call is not: there is no network in this
environment to verify it against.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import secrets
import time
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol

from app.services.alert_stream import AlertNotification
from app.services.correlator import Severity
from app.services.webhook_targets import (
    BlockedTarget,
    SecretVault,
    WebhookTarget,
    resolve_host,
    validate_webhook_url,
)

__all__ = [
    "DELIVERY_HEADER",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_TIMEOUT_SECONDS",
    "EVENT_HEADER",
    "EVENT_NAME",
    "REPLAY_WINDOW_SECONDS",
    "SIGNATURE_VERSION",
    "DeliveryAttempt",
    "DeliveryReport",
    "RetryPolicy",
    "SignatureCheck",
    "WebhookRequest",
    "WebhookResponse",
    "WebhookSender",
    "WebhookTransport",
    "WebhookTransportError",
    "alert_event",
    "dispatch",
    "event_body",
    "parse_signature_header",
    "sign_body",
    "verify_signature",
]

#: The signature header, Stripe-style: ``t=<unix>,v1=<hex>``. A version prefix
#: and an explicit timestamp, because a bare digest gives a receiver nothing to
#: check a replay against and no way to rotate the scheme.
SIGNATURE_HEADER = "X-AEGIS-Signature"

#: The event's name and the delivery's identity, so a receiver can route and
#: deduplicate without parsing the alert.
EVENT_HEADER = "X-AEGIS-Event"
DELIVERY_HEADER = "X-AEGIS-Delivery"
TIMESTAMP_HEADER = "X-AEGIS-Timestamp"

SIGNATURE_VERSION = "v1"
EVENT_NAME = "alert.created"

#: A receiver should refuse a signature older than this (measured in seconds).
#: If a retry's backoff ever exceeds it, the receiver will refuse the retry --
#: which is the correct outcome for a five-minute-old alert, and the reason the
#: backoff budget and this window are both bounded and documented together.
REPLAY_WINDOW_SECONDS = 300

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_TIMEOUT_SECONDS = 10.0

#: Statuses that mean "try again": the request was not refused on its merits.
#: 408 request timeout, 425 too early, 429 rate limited; every 5xx is added.
RETRYABLE_STATUSES: frozenset[int] = frozenset({408, 425, 429})


class WebhookTransportError(Exception):
    """A transport could not complete the request.

    Carries a short reason code (``timeout``, ``connection_refused``,
    ``tls_error``) rather than a message built from the URL or the response, so
    the record that reaches the log cannot leak either.
    """

    def __init__(self, reason: str) -> None:
        """Record the reason code."""
        super().__init__(f"webhook transport failed: {reason}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class WebhookRequest:
    """One signed request, with its destination already decided.

    Attributes:
        url: the URL to sign and address, for the ``Host`` header and the TLS
            SNI. The host in it is *not* to be resolved -- ``address`` is.
        address: the pinned IP to connect to, checked against R-55 immediately
            before this request was built.
        port: the port to connect to.
        body: the exact signed bytes.
        headers: every header, including the signature, as an immutable snapshot
            of the values that were signed. A live reference would let a later
            edit change what a transport reads after the fact.
        timeout: seconds the transport may take.
    """

    url: str
    address: str
    port: int
    body: bytes
    headers: Mapping[str, str]
    timeout: float


@dataclass(frozen=True, slots=True)
class WebhookResponse:
    """What a transport reports back: a status code and nothing else.

    The body is deliberately not carried. It is not part of any decision this
    module makes, and a received body in a log or an exception is exactly the
    kind of thing R-58 forbids.
    """

    status: int


class WebhookTransport(Protocol):
    """The HTTP client, narrowed to the one call this module makes."""

    def post(self, request: WebhookRequest) -> WebhookResponse:
        """POST a signed body to the request's pinned address.

        Connect to ``request.address``, present ``request.url``'s host in the
        ``Host`` header and TLS SNI, enforce ``request.timeout``, and follow no
        redirects -- a redirect to a private address would undo everything R-55
        just checked.

        Raises:
            WebhookTransportError: on a connection, TLS or timeout failure.
        """
        ...


def _is_success(status: int) -> bool:
    """Whether the receiver accepted the delivery."""
    return 200 <= status < 300


def must_retry(status: int) -> bool:
    """Whether a status code is worth another attempt.

    Retryable: the named overload statuses, every 5xx, and anything outside the
    2xx/4xx bands (a redirect is a configuration problem, and a 1xx is not a
    response). A 4xx that is not named is the receiver saying no.
    """
    return status in RETRYABLE_STATUSES or status >= 500 or status < 200 or 300 <= status < 400


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How many attempts, and how long between them.

    Attributes:
        max_attempts: total attempts including the first; 1 disables retries.
        base_seconds: the first backoff's upper bound.
        factor: growth per attempt.
        max_seconds: the cap on any single backoff.
    """

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    base_seconds: float = 1.0
    factor: float = 2.0
    max_seconds: float = 60.0

    def __post_init__(self) -> None:
        """Refuse a policy that would not be bounded, or would not work."""
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1, got {self.max_attempts}")
        if self.base_seconds <= 0:
            raise ValueError(f"base_seconds must be positive, got {self.base_seconds}")
        if self.factor < 1:
            raise ValueError(f"factor must be at least 1, got {self.factor}")
        if self.max_seconds < self.base_seconds:
            raise ValueError(
                f"max_seconds ({self.max_seconds}) must be at least base_seconds "
                f"({self.base_seconds})"
            )

    def bounds(self) -> tuple[float, ...]:
        """The backoff upper bound before each attempt after the first."""
        return tuple(
            min(self.base_seconds * self.factor**attempt, self.max_seconds)
            for attempt in range(self.max_attempts - 1)
        )

    def delay(self, attempt: int, *, jitter: Callable[[], float] = random.random) -> float:
        """The backoff before ``attempt`` (1-based, so attempt 1 has no delay).

        Full jitter -- a uniform draw in ``[0, bound]`` rather than ``bound``
        itself -- because a fleet retrying a recovered receiver in lockstep is a
        self-inflicted thundering herd.
        """
        if attempt < 2:
            return 0.0
        bound = self.bounds()[attempt - 2]
        return bound * jitter()

    def total_budget(self) -> float:
        """The most a caller can wait in backoffs for one delivery."""
        return sum(self.bounds())


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    """One attempt and its outcome.

    Attributes:
        attempt: 1-based position in the delivery.
        outcome: ``delivered``, ``retry``, ``rejected``, ``blocked`` or
            ``transport_error``.
        status: the HTTP status when there was one.
        delay_before: seconds waited before this attempt.
        reason: a short code for a failure, never a message from the peer.
    """

    attempt: int
    outcome: str
    status: int | None
    delay_before: float
    reason: str


@dataclass(frozen=True, slots=True)
class DeliveryReport:
    """What happened to one alert-to-target delivery.

    Attributes:
        delivery_id: the id carried in the ``X-AEGIS-Delivery`` header, so a
            receiver's log and this record can be joined.
        target_id: which target.
        delivered: whether a receiver accepted it.
        attempts: every attempt in order; empty when the delivery was skipped.
        skipped: the reason it was never attempted (``below_floor``,
            ``inactive``, ``unknown_severity``), or ``None``.
    """

    delivery_id: str
    target_id: str
    delivered: bool
    attempts: tuple[DeliveryAttempt, ...]
    skipped: str | None = None

    @property
    def attempt_count(self) -> int:
        """How many requests were made."""
        return len(self.attempts)

    @property
    def waited_seconds(self) -> float:
        """Total time spent in backoffs."""
        return sum(item.delay_before for item in self.attempts)


def sign_body(secret: str, body: bytes, *, timestamp: int) -> str:
    """Sign a body for the ``X-AEGIS-Signature`` header.

    The signed input is ``"<timestamp>.<body>"`` as bytes: the timestamp is
    inside the MAC, so a receiver cannot be tricked into accepting an old body
    with a fresh timestamp.
    """
    mac = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256)
    return f"t={timestamp},{SIGNATURE_VERSION}={mac.hexdigest()}"


@dataclass(frozen=True, slots=True)
class ParsedSignature:
    """A parsed signature header."""

    timestamp: int
    version: str
    digest: str


def parse_signature_header(header: str) -> ParsedSignature:
    """Parse ``t=<unix>,v1=<hex>``.

    Raises:
        ValueError: if the header is empty, has no timestamp, has no digest for
            a version this module knows, or carries a non-numeric timestamp.
            The caller turns this into a refusal rather than a partial check.
    """
    fields: dict[str, str] = {}
    for part in header.split(","):
        key, separator, value = part.strip().partition("=")
        if separator:
            fields[key.strip()] = value.strip()
    raw_timestamp = fields.get("t")
    digest = fields.get(SIGNATURE_VERSION)
    if not raw_timestamp or not digest:
        msg = f"signature must carry both t= and {SIGNATURE_VERSION}="
        raise ValueError(msg)
    try:
        timestamp = int(raw_timestamp)
    except ValueError as exc:
        msg = "signature timestamp must be an integer number of seconds"
        raise ValueError(msg) from exc
    unknown = {key for key in fields if key not in {"t", SIGNATURE_VERSION}}
    if unknown:
        # A version this receiver does not implement: refuse rather than verify
        # whatever it can parse, which is how a downgrade gets in.
        msg = f"signature carries unsupported field(s): {', '.join(sorted(unknown))}"
        raise ValueError(msg)
    return ParsedSignature(timestamp=timestamp, version=SIGNATURE_VERSION, digest=digest)


@dataclass(frozen=True, slots=True)
class SignatureCheck:
    """The result of verifying a signature, with the reason when it fails."""

    valid: bool
    reason: str


def verify_signature(
    secret: str,
    body: bytes,
    header: str | None,
    *,
    now: datetime,
    tolerance_seconds: int = REPLAY_WINDOW_SECONDS,
) -> SignatureCheck:
    """Verify a received body against its signature header.

    This is the documented scheme's reference implementation, and it is what the
    tests use to prove a delivery is verifiable by a receiver. It is written to be
    usable by one: no exceptions escape, and the reason is a short code.

    Args:
        secret: the shared signing secret.
        body: the exact bytes received.
        header: the ``X-AEGIS-Signature`` value, or ``None``.
        now: the receiver's clock, timezone-aware.
        tolerance_seconds: how old a signature may be.

    Returns:
        ``valid=True``, or ``valid=False`` with a reason of ``missing_header``,
        ``malformed_header``, ``timestamp_out_of_window`` or ``digest_mismatch``.
    """
    if not header:
        return SignatureCheck(valid=False, reason="missing_header")
    try:
        parsed = parse_signature_header(header)
    except ValueError:
        return SignatureCheck(valid=False, reason="malformed_header")
    drift = abs(int(now.timestamp()) - parsed.timestamp)
    if drift > tolerance_seconds:
        return SignatureCheck(valid=False, reason="timestamp_out_of_window")
    expected = hmac.new(
        secret.encode(), str(parsed.timestamp).encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, parsed.digest):
        return SignatureCheck(valid=False, reason="digest_mismatch")
    return SignatureCheck(valid=True, reason="ok")


def alert_event(
    notification: AlertNotification,
    *,
    delivery_id: str,
    at: datetime,
) -> dict[str, object]:
    """The event document for one alert.

    The alert is the same row the query API returns, so a receiver stores what
    the dashboard shows. The stream's sequence number is deliberately absent: it
    is a position in an in-process stream, and a receiver that keyed on it would
    be keyed on something that restarts.
    """
    return {
        "event": EVENT_NAME,
        "delivery": delivery_id,
        "sent_at": at.isoformat(),
        "alert": notification.alert.model_dump(mode="json"),
    }


def event_body(document: Mapping[str, object]) -> bytes:
    """Canonicalise a document into the bytes that are signed and sent.

    Sorted keys and compact separators, so the bytes are a function of the
    document rather than of a serializer's mood.
    """
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


class WebhookSender:
    """Delivers alert events to targets, with bounded retries.

    Every collaborator is injected -- the transport, the clock, the sleep, the
    jitter, the logger -- so the retry policy is tested without waiting and the
    decision logic is tested without a network.
    """

    __slots__ = (
        "_allowlist",
        "_clock",
        "_jitter",
        "_log",
        "_policy",
        "_resolver",
        "_sleep",
        "_timeout",
        "_transport",
        "_vault",
    )

    def __init__(
        self,
        transport: WebhookTransport,
        vault: SecretVault,
        allowlist: Collection[str],
        *,
        resolver: Callable[[str, int], Sequence[str]] = resolve_host,
        policy: RetryPolicy | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        jitter: Callable[[], float] = random.random,
        log: Callable[[Mapping[str, object]], None] | None = None,
    ) -> None:
        """Wire the transport, the vault, the allowlist and the retry policy.

        Args:
            transport: the HTTP client.
            vault: opens the target's sealed secret.
            allowlist: permitted hostnames (R-55), re-checked per attempt.
            resolver: the DNS lookup, injected so tests resolve nothing.
            policy: how many attempts, and how long between them.
            timeout: seconds any single attempt may take.
            sleep: the backoff sleeper, injected so tests do not wait.
            clock: the clock the delivery id and timestamp come from.
            jitter: the draw, uniform in ``[0, 1]``, applied to each backoff.
            log: a sink for delivery records; ``None`` logs nothing.

        Raises:
            ValueError: if the timeout is not positive.
        """
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")
        self._transport = transport
        self._vault = vault
        self._allowlist = tuple(allowlist)
        self._resolver = resolver
        self._policy = policy or RetryPolicy()
        self._timeout = timeout
        self._sleep = sleep
        self._clock = clock
        self._jitter = jitter
        self._log = log

    def _skip_reason(self, target: WebhookTarget, notification: AlertNotification) -> str | None:
        """Why this target must not receive this alert, or ``None`` to send.

        Checked before the secret is opened and before anything is signed: a
        delivery that never happens should not touch the vault at all.
        """
        if not target.active:
            return "inactive"
        severity = _severity_of(notification)
        if severity is None:
            return "unknown_severity"
        if not target.receives(severity):
            return "below_floor"
        return None

    def deliver(self, target: WebhookTarget, notification: AlertNotification) -> DeliveryReport:
        """Deliver one alert to one target, retrying within the policy.

        Args:
            target: the destination, carrying its sealed secret.
            notification: the alert, in the shape the query API returns.

        Returns:
            The report: whether it was delivered, and every attempt made. A
            target that does not receive this severity is reported as skipped
            rather than sent and rather than ignored -- a dashboard that shows
            "5 targets, 2 delivered, 3 below floor" is how an operator tells a
            quiet endpoint from a misconfigured floor.

        Raises:
            SecretUnreadable: if the target's sealed secret cannot be opened with
                the current application key. Raised rather than retried: no
                number of attempts makes a rotated key work, and a silent failure
                here would look like a receiver problem.
        """
        skip = self._skip_reason(target, notification)
        if skip is not None:
            return DeliveryReport(
                delivery_id="",
                target_id=target.id,
                delivered=False,
                attempts=(),
                skipped=skip,
            )

        delivery_id = _delivery_id(self._clock)
        timestamp = int(self._clock())
        secret = self._vault.open(target.secret_token)
        document = alert_event(notification, delivery_id=delivery_id, at=datetime.now(UTC))
        body = event_body(document)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "aegis-webhook/1",
            EVENT_HEADER: EVENT_NAME,
            DELIVERY_HEADER: delivery_id,
            TIMESTAMP_HEADER: str(timestamp),
            SIGNATURE_HEADER: sign_body(secret, body, timestamp=timestamp),
        }

        attempts: list[DeliveryAttempt] = []
        for attempt in range(1, self._policy.max_attempts + 1):
            delay = self._policy.delay(attempt, jitter=self._jitter)
            if delay:
                self._sleep(delay)
            outcome, status, reason = self._attempt(target, body, headers)
            attempts.append(
                DeliveryAttempt(
                    attempt=attempt,
                    outcome=outcome,
                    status=status,
                    delay_before=delay,
                    reason=reason,
                )
            )
            self._emit(
                {
                    "event": "webhook.attempt",
                    "delivery": delivery_id,
                    "target": target.id,
                    "attempt": attempt,
                    "outcome": outcome,
                    "status": status,
                    "reason": reason,
                }
            )
            if outcome == "delivered":
                return self._report(delivery_id, target.id, attempts)
            if outcome in {"rejected", "blocked"}:
                break

        return self._report(delivery_id, target.id, attempts)

    def _attempt(
        self, target: WebhookTarget, body: bytes, headers: Mapping[str, str]
    ) -> tuple[str, int | None, str]:
        """Validate the destination, make one request, and classify the result.

        Validation is redone here -- every attempt, not once at registration --
        so an address that has since changed to a private one is refused instead
        of dialled. A name that no longer resolves is retried: that is a network
        condition, not a configuration one.
        """
        try:
            validated = validate_webhook_url(
                target.url, allowlist=self._allowlist, resolver=self._resolver
            )
        except BlockedTarget as exc:
            reason = f"{exc.reason}:{exc.detail}" if exc.detail else exc.reason
            if exc.reason == "unresolvable_host":
                return "retry", None, reason
            return "blocked", None, reason
        request = WebhookRequest(
            url=validated.url,
            address=validated.pinned,
            port=validated.port,
            body=body,
            headers=MappingProxyType(dict(headers)),
            timeout=self._timeout,
        )
        try:
            response = self._transport.post(request)
        except WebhookTransportError as exc:
            return "transport_error", None, exc.reason
        except TimeoutError:
            return "transport_error", None, "timeout"
        if _is_success(response.status):
            return "delivered", response.status, "ok"
        if must_retry(response.status):
            return "retry", response.status, "retryable_status"
        return "rejected", response.status, "receiver_refused"

    def _report(
        self, delivery_id: str, target_id: str, attempts: list[DeliveryAttempt]
    ) -> DeliveryReport:
        """Summarise a delivery and log the summary."""
        delivered = bool(attempts) and attempts[-1].outcome == "delivered"
        report = DeliveryReport(
            delivery_id=delivery_id,
            target_id=target_id,
            delivered=delivered,
            attempts=tuple(attempts),
        )
        self._emit(
            {
                "event": "webhook.delivery",
                "delivery": delivery_id,
                "target": target_id,
                "delivered": delivered,
                "attempts": report.attempt_count,
                "waited_seconds": round(report.waited_seconds, 3),
            }
        )
        return report

    def _emit(self, record: Mapping[str, object]) -> None:
        """Hand a record to the logger, if one was configured."""
        if self._log is not None:
            self._log(record)


def _severity_of(notification: AlertNotification) -> Severity | None:
    """The alert's severity, or ``None`` when this build does not know it.

    A severity the band table cannot place cannot be compared against a floor,
    and guessing -- treating it as critical, or as info -- would either spam a
    receiver or drop a real alert. Callers report instead of sending.
    """
    try:
        return Severity(str(notification.alert.severity))
    except ValueError:
        return None


def _delivery_id(clock: Callable[[], float]) -> str:
    """An id unique enough to join a receiver's log with ours.

    Seeded from the clock plus 48 random bits: two deliveries in the same second
    must not share an id, and a receiver uses this to deduplicate. The random
    part comes from :mod:`secrets` rather than :mod:`random`, because an id a
    receiver deduplicates on is a value an attacker would rather guess than
    collide with -- and a predictable one makes every retry's id guessable.
    """
    return f"{int(clock()):x}-{secrets.token_hex(6)}"


def dispatch(
    notification: AlertNotification,
    targets: Iterable[WebhookTarget],
    sender: WebhookSender,
) -> tuple[DeliveryReport, ...]:
    """Send one alert to every target whose severity floor it meets (FR-21).

    The floor lives in :meth:`WebhookSender.deliver`, so it applies however a
    target is reached; this function's job is to fan out and hand back one
    report per target, in the order given.

    Args:
        notification: the alert to send.
        targets: every configured target.
        sender: the delivery machinery.

    Returns:
        One report per target, in the order given.
    """
    return tuple(sender.deliver(target, notification) for target in targets)
