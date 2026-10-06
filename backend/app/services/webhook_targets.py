"""Where a webhook may point, and how its signing secret is kept (T-311).

R-55 requires two controls and this module is both: outbound webhook URLs are
validated **against an allowlist**, and private/link-local ranges are refused.
Three decisions make that a control rather than a gesture.

**The address check is on the resolved address, not the name.** A hostname is
not an address, and ``https://rebind.example.com`` is the whole attack: it
resolves to a public address when a validator looks and to ``127.0.0.1`` when the
client connects. So validation resolves the host and refuses if **any** address
it resolves to is not globally routable; the accepted addresses are returned so
the transport can connect to the one that was checked (pinning), which closes the
window between check and connect.

**The allowlist fails closed and refuses to be decorative.** An empty allowlist
permits nothing, and an entry that is a bare wildcard, contains a scheme, a port
or a path, or has embedded whitespace is refused when it is *configured* -- an
allowlist containing ``*`` looks like policy and behaves like neither.

**A signing secret is stored sealed.** HMAC is symmetric, so the secret has to be
recoverable to sign with it -- hashing it would make delivery impossible -- which
means the row holds it encrypted rather than in the clear. The key is derived
from ``AEGIS_SECRET_KEY``, so the consequence is named rather than discovered:
rotating the application secret makes existing webhook secrets unreadable, and
they must be re-issued.
"""

from __future__ import annotations

import base64
import ipaddress
import secrets
import socket
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.services.correlator import Severity

__all__ = [
    "MIN_SECRET_BYTES",
    "BlockedTarget",
    "AllowlistError",
    "InMemoryWebhookStore",
    "RegisteredTarget",
    "ResolvedAddress",
    "SecretUnreadable",
    "SecretVault",
    "ValidatedTarget",
    "WebhookStore",
    "WebhookTarget",
    "host_is_allowlisted",
    "parse_allowlist",
    "security_verdict_of_address",
    "validate_webhook_url",
]

#: 32 bytes of urandom, base64url-encoded: enough entropy that guessing is not
#: the cheapest way in, and short enough for an operator to copy out of the UI.
MIN_SECRET_BYTES = 32


class BlockedTarget(ValueError):
    """The URL cannot be delivered to, and the reason is safe to show a user.

    The reason is a short code rather than a message built from the URL: a
    webhook URL may carry a token in its path or query, and R-58 keeps alert
    infrastructure out of error text that clients see.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        """Record the machine-readable reason and an optional safe detail."""
        super().__init__(f"webhook target refused: {reason}" + (f" ({detail})" if detail else ""))
        self.reason = reason
        self.detail = detail


class AllowlistError(ValueError):
    """An allowlist entry is malformed, caught when it is configured."""


class SecretUnreadable(ValueError):
    """A sealed secret cannot be opened with the current application key."""


@dataclass(frozen=True, slots=True)
class ResolvedAddress:
    """One address the host resolved to, and whether it may be connected to."""

    address: str
    permitted: bool
    reason: str

    @property
    def family(self) -> int:
        """``4`` or ``6``, for a transport that has to pick a socket family."""
        return int(ipaddress.ip_address(self.address).version)


def security_verdict_of_address(address: str) -> tuple[bool, str]:
    """Whether a single resolved address may be connected to, and why not.

    Public rather than private because it is R-55's decision point and the place
    a regression would be invisible: a caller that swallowed the refusal would
    still refuse nothing, and a test can only pin the classes it can call.

    ``is_global`` is the accept rather than a list of ranges, because the list is
    the thing that goes stale: it covers loopback, private, link-local, CGNAT,
    reserved and IPv6 site-local, and it also refuses the ranges a carefully
    written list forgets -- IPv4-mapped IPv6 such as ``::ffff:127.0.0.1`` and the
    documentation networks. It is not sufficient on its own: CPython reports
    IPv4 multicast (224/4) as global, so the multicast class is refused before it.

    Returns:
        ``(True, "")`` for an address that may be dialled, else ``(False, why)``
        with ``why`` one of ``not_an_address``, ``loopback``, ``link_local``,
        ``multicast``, ``unspecified``, ``private``, ``not_globally_routable``.
    """
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False, "not_an_address"
    # The specific reason first, so a refusal names what is wrong; the multicast
    # check is not redundant with is_global, which reports multicast addresses as
    # globally routable -- they are, in the routing sense, and not somewhere an
    # alert webhook may be sent.
    if parsed.is_loopback:
        return False, "loopback"
    if parsed.is_link_local:
        return False, "link_local"
    if parsed.is_multicast:
        return False, "multicast"
    if parsed.is_unspecified:
        return False, "unspecified"
    if parsed.is_private:
        return False, "private"
    if not parsed.is_global:
        return False, "not_globally_routable"
    return True, ""


def _parse_entry(entry: str) -> str:
    """Validate one allowlist entry and return it normalised.

    Raises:
        AllowlistError: if the entry is empty, a bare wildcard, or carries
            anything but a hostname (a scheme, port, path or whitespace).
    """
    cleaned = entry.strip().lower().rstrip(".")
    if not cleaned:
        raise AllowlistError("allowlist entries must not be empty")
    if cleaned == "*":
        raise AllowlistError(
            "a bare '*' allowlist entry would permit every host, which is not an allowlist"
        )
    if cleaned.startswith("*."):
        remainder = cleaned[2:]
        if not remainder or "*" in remainder:
            raise AllowlistError(f"allowlist entry {entry!r} has a malformed wildcard")
        return f"*.{remainder}"
    if "*" in cleaned or "/" in cleaned or ":" in cleaned or " " in cleaned:
        raise AllowlistError(
            f"allowlist entry {entry!r} must be a hostname (optional '*.', no scheme, port or path)"
        )
    return cleaned


def parse_allowlist(raw: str | Iterable[str]) -> tuple[str, ...]:
    """Parse an allowlist from a comma-separated string or an iterable.

    An empty or whitespace-only string is an empty allowlist, not a malformed
    one: it is the default configuration, and it denies every host. That is the
    fail-closed reading of "no hosts configured" (R-55) rather than an accident
    of string handling. An empty entry *between* entries is still an error.

    Returns:
        Normalised entries, deduplicated, in the order given.

    Raises:
        AllowlistError: if any entry is malformed. Raised at startup rather than
            at delivery time, because a bad allowlist is a configuration defect
            and the failing request would be a live alert.
    """
    if isinstance(raw, str) and not raw.strip():
        return ()
    entries = raw.split(",") if isinstance(raw, str) else list(raw)
    seen: dict[str, None] = {}
    for entry in entries:
        cleaned = _parse_entry(entry)
        seen.setdefault(cleaned, None)
    return tuple(seen)


def host_is_allowlisted(host: str, allowlist: Collection[str]) -> bool:
    """Whether a hostname is permitted by the allowlist.

    An entry matches the host itself, or one label beneath it when written as
    ``*.example.com`` -- one label, not any depth, and never the bare domain, so
    the entry describes exactly what it permits. Matching is on the whole
    remaining label sequence, so ``evil-example.com`` cannot match ``example.com``.
    """
    candidate = host.strip().lower().rstrip(".")
    for entry in allowlist:
        if entry == candidate:
            return True
        if entry.startswith("*."):
            suffix = entry[1:]  # ".example.com"
            if candidate.endswith(suffix) and "." not in candidate[: -len(suffix)]:
                return True
    return False


def resolve_host(host: str, port: int) -> Sequence[str]:
    """Resolve a hostname to every address it currently has.

    Raises:
        OSError: if the name does not resolve. Propagated rather than swallowed
            so the caller can turn it into a refusal that names the host class
            and nothing about the resolver's internals.
    """
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return tuple(dict.fromkeys(str(info[4][0]) for info in infos))


@dataclass(frozen=True, slots=True)
class ValidatedTarget:
    """A URL that passed both controls, with the addresses that were checked.

    Attributes:
        url: the URL as configured.
        host: the normalised hostname.
        port: the effective port (443 when the URL omits one).
        addresses: every address the host resolved to, each with its verdict.
        pinned: the first permitted address, for the transport to connect to.
    """

    url: str
    host: str
    port: int
    addresses: tuple[ResolvedAddress, ...]
    pinned: str


def validate_webhook_url(
    url: str,
    *,
    allowlist: Collection[str],
    resolver: Callable[[str, int], Sequence[str]] = resolve_host,
) -> ValidatedTarget:
    """Validate an outbound webhook URL against R-55's two controls.

    Args:
        url: the URL to validate.
        allowlist: permitted hostnames, already parsed by :func:`parse_allowlist`.
        resolver: the DNS lookup, injected so tests never depend on a name
            resolving and so a rebinding host can be simulated exactly.

    Returns:
        The validated target, including every address that was checked and the
        address the transport should connect to.

    Raises:
        BlockedTarget: with a reason code, on anything that would make the
            request leave the trust boundary: a non-HTTPS scheme, credentials in
            the URL, a host that is not allowlisted, a host that does not
            resolve, or an address that is not globally routable. A host with
            several addresses is refused if *any* of them is not.
    """
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https":
        # Not http: the body carries alert content (R-58), which must not cross
        # the internet in the clear.
        raise BlockedTarget("scheme_not_https", f"scheme {parts.scheme or '(none)'!r}")
    if parts.username or parts.password:
        raise BlockedTarget("credentials_in_url")
    if parts.fragment:
        raise BlockedTarget("fragment_in_url")
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise BlockedTarget("missing_host")
    try:
        port = parts.port or 443
    except ValueError as exc:  # a port that is not a number, or out of range
        raise BlockedTarget("invalid_port") from exc

    if not host_is_allowlisted(host, allowlist):
        raise BlockedTarget("host_not_allowlisted")

    try:
        addresses = resolver(host, port)
    except OSError as exc:
        raise BlockedTarget("unresolvable_host") from exc
    if not addresses:
        raise BlockedTarget("unresolvable_host")

    resolved = tuple(
        ResolvedAddress(address=address, permitted=verdict[0], reason=verdict[1])
        for address in addresses
        for verdict in (security_verdict_of_address(address),)
    )
    refused = [item for item in resolved if not item.permitted]
    if refused:
        # Any prohibited address refuses the whole target: a name that resolves
        # to one public and one private address is exactly the rebinding case.
        raise BlockedTarget("forbidden_address", refused[0].reason)
    return ValidatedTarget(
        url=url.strip(),
        host=host,
        port=port,
        addresses=resolved,
        pinned=resolved[0].address,
    )


#: Fernet tokens are authenticated: a sealed secret that was truncated, edited
#: or encrypted under another key fails to open rather than returning garbage.
_SECRET_SALT = b"aegis.webhook.secret.v1"


class SecretVault:
    """Seals and opens webhook signing secrets with a key from the app secret.

    The derived key is per-deployment: two environments with different
    ``AEGIS_SECRET_KEY`` values cannot read each other's sealed secrets, which is
    the intended consequence and the reason a restore into another environment
    needs the webhooks re-issued rather than the database copied.
    """

    __slots__ = ("_fernet",)

    def __init__(self, app_secret: str) -> None:
        """Derive the sealing key from the application secret.

        Raises:
            ValueError: if the application secret is too short to be a key
                source. The settings validator already refuses weak secrets;
                this is the library-level check.
        """
        if len(app_secret) < 32:
            msg = "app_secret must be at least 32 characters to derive a sealing key"
            raise ValueError(msg)
        derived = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_SECRET_SALT,
            info=b"webhook-signing",
        ).derive(app_secret.encode())
        self._fernet = Fernet(base64.urlsafe_b64encode(derived))

    @staticmethod
    def generate_secret() -> str:
        """A fresh signing secret, shown to the operator exactly once."""
        return secrets.token_urlsafe(MIN_SECRET_BYTES)

    def seal(self, secret: str) -> str:
        """Encrypt a signing secret for storage."""
        return self._fernet.encrypt(secret.encode()).decode()

    def open(self, token: str) -> str:
        """Decrypt a stored signing secret.

        Raises:
            SecretUnreadable: if the token was not sealed by this key -- a
                rotated application secret, a different environment, or a
                corrupted row. Never returns a partial or empty secret.
        """
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except (InvalidToken, ValueError) as exc:
            msg = "sealed secret cannot be opened with this application key"
            raise SecretUnreadable(msg) from exc


@dataclass(frozen=True, slots=True)
class WebhookTarget:
    """One configured destination for alert events.

    Attributes:
        id: opaque identifier, stable across restarts.
        url: the validated destination.
        description: operator note, never sent anywhere.
        severity_floor: the lowest severity this target receives (FR-21's
            ``high``/``critical``, expressed as a floor so a deployment can
            raise it without a code change).
        secret_token: the signing secret, **sealed**. The plaintext exists only
            in the response that created the target and in memory while a
            delivery is signed.
        created_at: timezone-aware creation time.
        active: whether deliveries are attempted; a disabled target keeps its
            configuration and its history.
    """

    id: str
    url: str
    description: str | None
    severity_floor: Severity
    secret_token: str
    created_at: datetime
    active: bool = True

    def __post_init__(self) -> None:
        """Refuse a target that cannot be delivered to or identified."""
        if not self.id.strip():
            raise ValueError("a webhook target needs an id")
        if not self.url.strip():
            raise ValueError("a webhook target needs a url")
        if not self.secret_token.strip():
            raise ValueError(
                "a webhook target must carry a sealed secret; without one it cannot be signed"
            )
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware, got a naive timestamp")

    def receives(self, severity: Severity) -> bool:
        """Whether an alert of this severity goes to this target (FR-21)."""
        return self.active and severity.rank >= self.severity_floor.rank


@dataclass(frozen=True, slots=True)
class RegisteredTarget:
    """A newly created target and the secret the operator sees once.

    The plaintext is deliberately not a field on :class:`WebhookTarget`: the row
    that the store keeps cannot leak what it does not hold.
    """

    target: WebhookTarget
    secret: str


class WebhookStore(Protocol):
    """Where webhook configuration lives.

    Small on purpose: the policy -- validation, floors, sealing -- is this
    module's, and swapping the dictionary for a table is a storage change rather
    than a behaviour change.
    """

    def add(self, target: WebhookTarget) -> None:
        """Store a target."""
        ...

    def list(self) -> tuple[WebhookTarget, ...]:
        """Every target, oldest first."""
        ...

    def get(self, target_id: str) -> WebhookTarget | None:
        """One target, or ``None``."""
        ...

    def remove(self, target_id: str) -> bool:
        """Delete a target. Returns whether it existed."""
        ...


class InMemoryWebhookStore:
    """A :class:`WebhookStore` in a dictionary, for tests and single-process runs.

    Webhook configuration is small and changes rarely, but it is not ephemeral in
    production: a restart that forgets a target stops delivering alerts, so the
    persistent store is a table and this is the stand-in that lets the policy be
    tested without one.
    """

    __slots__ = ("_by_id", "_order")

    def __init__(self) -> None:
        """Start empty."""
        self._by_id: dict[str, WebhookTarget] = {}
        self._order: list[str] = []

    def add(self, target: WebhookTarget) -> None:
        """Store a target, keeping insertion order for listing."""
        if target.id not in self._by_id:
            self._order.append(target.id)
        self._by_id[target.id] = target

    def list(self) -> tuple[WebhookTarget, ...]:
        """Every target, oldest first."""
        return tuple(
            self._by_id[target_id] for target_id in self._order if target_id in self._by_id
        )

    def get(self, target_id: str) -> WebhookTarget | None:
        """One target, or ``None``."""
        return self._by_id.get(target_id)

    def remove(self, target_id: str) -> bool:
        """Delete a target. Returns whether it existed."""
        if target_id not in self._by_id:
            return False
        del self._by_id[target_id]
        self._order.remove(target_id)
        return True
