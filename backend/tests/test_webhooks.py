"""T-311: outbound webhooks -- R-55 controls, signing, bounded retries (FR-21).

The three acceptance criteria are asserted directly rather than approximated:

* **Private ranges are refused.** Every reserved class is exercised by address,
  including the two that a naive ``is_global`` check gets wrong -- IPv4
  multicast (224/4 is "global" to CPython) and IPv6 transition addresses -- and
  the *rebinding* case, where a name resolves to one permitted address and one
  refused one, is asserted to refuse the whole target.
* **The signature is verifiable with the documented scheme.** The test does not
  call :func:`verify_signature` against a header the same module produced: it
  rebuilds the digest with :func:`hmac.new` from the wire bytes, which is what a
  receiver's own code does.
* **Retries are bounded and logged.** A dead endpoint is driven to exhaustion and
  the attempt count is asserted to equal the policy, not merely to be "more than
  one"; the log records are asserted to carry no URL, no secret and no alert
  content (R-58).

The transport is injected everywhere, so no test opens a socket, and the resolver
is injected, so no test depends on a name resolving.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.db.models import AlertStatus
from app.main import create_app
from app.schemas.query import AlertRow
from app.services.alert_stream import AlertNotification
from app.services.correlator import Severity
from app.services.webhook_delivery import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    EVENT_NAME,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    DeliveryReport,
    RetryPolicy,
    WebhookRequest,
    WebhookResponse,
    WebhookSender,
    WebhookTransportError,
    alert_event,
    dispatch,
    event_body,
    parse_signature_header,
    sign_body,
    verify_signature,
)
from app.services.webhook_targets import (
    MIN_SECRET_BYTES,
    AllowlistError,
    BlockedTarget,
    InMemoryWebhookStore,
    SecretUnreadable,
    SecretVault,
    WebhookTarget,
    host_is_allowlisted,
    parse_allowlist,
    security_verdict_of_address,
    validate_webhook_url,
)
from fastapi.testclient import TestClient

SECRET = "s" * 48
#: A settings-valid application secret (the entropy check in Settings refuses a
#: repeated character), used wherever an application is built.
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
SIGNING_SECRET = "sign-this-please-0123456789abcdef"  # pragma: allowlist secret
AT = datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)
PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"

#: Every address class R-55 refuses, with the reason the refusal must name.
REFUSED_ADDRESSES: tuple[tuple[str, str], ...] = (
    ("127.0.0.1", "loopback"),
    ("::1", "loopback"),
    ("10.0.0.5", "private"),
    ("172.16.9.9", "private"),
    ("192.168.1.10", "private"),
    ("fd00::1", "private"),
    ("169.254.169.254", "link_local"),
    ("fe80::1", "link_local"),
    ("224.0.0.1", "multicast"),
    ("ff02::1", "multicast"),
    ("0.0.0.0", "unspecified"),  # noqa: S104 -- refused on purpose, not bound
    ("::", "unspecified"),
    ("100.64.0.1", "not_globally_routable"),
    # An IPv6 address that carries an IPv4 destination is judged by that
    # destination, so each of these must name the IPv4 class it embeds. The
    # loopback row is the one CI caught: CPython 3.11.10 and later call it
    # loopback, 3.11.2 called it private, and a verdict that moves with a
    # micro-release is not a control.
    ("::ffff:127.0.0.1", "loopback"),
    ("::ffff:169.254.169.254", "link_local"),
    ("::ffff:224.0.0.1", "multicast"),
    ("::ffff:100.64.0.1", "not_globally_routable"),
    ("::ffff:10.0.0.5", "private"),
    ("::127.0.0.1", "loopback"),
    ("::10.0.0.5", "private"),
    ("::224.0.0.1", "multicast"),
    ("::ffff:0:127.0.0.1", "loopback"),
    ("::ffff:0:10.0.0.5", "private"),
    ("64:ff9b::127.0.0.1", "loopback"),
    ("64:ff9b::10.0.0.5", "private"),
    ("64:ff9b::224.0.0.1", "multicast"),
)

#: IPv4 addresses whose verdict must not change when the address is embedded in
#: IPv6. Public addresses are in the table on purpose: unwrapping has to leave a
#: legitimate destination permitted, not merely refuse more.
EMBEDDED_PAIRS: tuple[tuple[str, str], ...] = (
    ("127.0.0.1", "::ffff:127.0.0.1"),
    ("127.0.0.1", "::127.0.0.1"),
    ("10.0.0.5", "::ffff:10.0.0.5"),
    ("169.254.169.254", "::ffff:169.254.169.254"),
    ("224.0.0.1", "::ffff:224.0.0.1"),
    ("100.64.0.1", "::ffff:100.64.0.1"),
    ("192.0.2.1", "::ffff:192.0.2.1"),
    ("93.184.216.34", "::ffff:93.184.216.34"),
    ("127.0.0.1", "::ffff:0:127.0.0.1"),
    ("10.0.0.5", "::ffff:0:10.0.0.5"),
    ("127.0.0.1", "64:ff9b::127.0.0.1"),
    ("10.0.0.5", "64:ff9b::10.0.0.5"),
    ("224.0.0.1", "64:ff9b::224.0.0.1"),
    ("93.184.216.34", "64:ff9b::93.184.216.34"),
)


def resolver_returning(*addresses: str) -> Any:  # noqa: ANN401 -- a stub, typed at use
    """A DNS stub that always answers with the given addresses."""

    def resolve(host: str, port: int) -> Sequence[str]:
        return list(addresses)

    return resolve


def raising_resolver(host: str = "hooks.example.com") -> Any:  # noqa: ANN401
    """A DNS stub that fails, as a name that does not resolve would."""

    def resolve(name: str, port: int) -> Sequence[str]:
        raise OSError(f"name resolution failed for {host}")

    return resolve


def row(alert_id: int = 1, *, severity: str = "high") -> AlertRow:
    """A valid alert row, the shape the query API returns."""
    return AlertRow(
        id=alert_id,
        created_at=AT,
        entity_id=7,
        family="Reconnaissance",
        severity=severity,
        score=0.91,
        status=AlertStatus.open.value,
        first_seen=AT,
        last_seen=AT,
        occurrence_count=1,
    )


def notification(severity: str = "high") -> AlertNotification:
    """An alert as the stream would publish it."""
    return AlertNotification(sequence=1, alert=row(severity=severity))


def seal(vault: SecretVault, secret: str = SIGNING_SECRET) -> str:
    """A sealed token for a target."""
    return vault.seal(secret)


def target(
    vault: SecretVault,
    *,
    url: str = "https://hooks.example.com/alerts",
    description: str | None = None,
    severity_floor: Severity = Severity.high,
    active: bool = True,
    id: str = "wh_1",  # noqa: A002 -- the field is named id
) -> WebhookTarget:
    """A stored target, sealed secret and all."""
    return WebhookTarget(
        id=id,
        url=url,
        description=description,
        severity_floor=severity_floor,
        secret_token=seal(vault),
        created_at=AT,
        active=active,
    )


@dataclass
class RecordingTransport:
    """A transport that records every request and replays a scripted status."""

    statuses: list[int | Exception] = field(default_factory=lambda: [200])
    requests: list[WebhookRequest] = field(default_factory=list)

    def post(self, request: WebhookRequest) -> WebhookResponse:
        """Record the request and answer with the scripted status."""
        self.requests.append(request)
        outcome = self.statuses[min(len(self.requests) - 1, len(self.statuses) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return WebhookResponse(status=outcome)


def sender_for(
    transport: RecordingTransport,
    vault: SecretVault,
    *,
    allowlist: Sequence[str] = ("hooks.example.com",),
    resolver: Any = None,  # noqa: ANN401 -- a stub
    policy: RetryPolicy | None = None,
    log: Any = None,  # noqa: ANN401 -- a list
) -> WebhookSender:
    """A sender wired for a test: no sleeping, no network, no real DNS."""
    return WebhookSender(
        transport,
        vault,
        allowlist,
        resolver=resolver if resolver is not None else resolver_returning(PUBLIC_V4),
        policy=policy or RetryPolicy(max_attempts=3),
        sleep=lambda seconds: None,
        jitter=lambda: 1.0,
        log=log,
    )


@pytest.fixture
def vault() -> SecretVault:
    return SecretVault(SECRET)


# --- the allowlist (R-55) ----------------------------------------------------


def test_allowlist_entries_are_normalised_and_deduplicated() -> None:
    assert parse_allowlist(" Hooks.Example.COM. , hooks.example.com,*.corp.example.com ") == (
        "hooks.example.com",
        "*.corp.example.com",
    )


def test_an_empty_allowlist_denies_every_host() -> None:
    """Fail-closed: no configured hosts is not a disabled check."""
    assert parse_allowlist("") == ()
    assert parse_allowlist("   ") == ()
    assert not host_is_allowlisted("hooks.example.com", parse_allowlist(""))


@pytest.mark.parametrize(
    "entry",
    [
        "*",
        "https://hooks.example.com",
        "hooks.example.com/path",
        "hooks.example.com:443",
        "a b",
        "*.",
        "*.*.example.com",
        "*example.com",
    ],
)
def test_a_malformed_allowlist_entry_fails_startup(entry: str) -> None:
    with pytest.raises(AllowlistError):
        parse_allowlist(entry)


def test_an_empty_entry_between_entries_is_malformed() -> None:
    """``a,,b`` is a typo, not a silent gap in the allowlist."""
    with pytest.raises(AllowlistError):
        parse_allowlist("hooks.example.com,,other.example.com")


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("hooks.example.com", True),
        ("hooks.example.com.evil.test", False),
        ("evil-hooks.example.com", False),
        ("notexample.com", False),
        ("example.com", False),
    ],
)
def test_an_exact_entry_matches_only_that_host(host: str, expected: bool) -> None:
    assert host_is_allowlisted(host, ("hooks.example.com",)) is expected


def test_a_wildcard_entry_matches_exactly_one_label_beneath() -> None:
    allowlist = parse_allowlist("*.corp.example.com")
    assert host_is_allowlisted("hooks.corp.example.com", allowlist)
    assert host_is_allowlisted("HOOKS.CORP.EXAMPLE.COM.", allowlist)
    assert not host_is_allowlisted("corp.example.com", allowlist)
    assert not host_is_allowlisted("a.b.corp.example.com", allowlist)
    assert not host_is_allowlisted("evilcorp.example.com", allowlist)


# --- URL validation: the SSRF control (R-55) ---------------------------------


def test_a_permitted_public_target_is_validated_and_pinned() -> None:
    validated = validate_webhook_url(
        "https://hooks.example.com/alerts",
        allowlist=("hooks.example.com",),
        resolver=resolver_returning(PUBLIC_V4, PUBLIC_V6),
    )
    assert validated.host == "hooks.example.com"
    assert validated.port == 443
    assert validated.pinned == PUBLIC_V4
    assert [item.address for item in validated.addresses] == [PUBLIC_V4, PUBLIC_V6]


def test_an_explicit_port_is_kept() -> None:
    validated = validate_webhook_url(
        "https://hooks.example.com:8443/alerts",
        allowlist=("hooks.example.com",),
        resolver=resolver_returning(PUBLIC_V4),
    )
    assert validated.port == 8443


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.com/alerts",
        "ftp://hooks.example.com/alerts",
        "hooks.example.com/alerts",
    ],
)
def test_a_non_https_url_is_refused(url: str) -> None:
    with pytest.raises(BlockedTarget) as excinfo:
        validate_webhook_url(
            url, allowlist=("hooks.example.com",), resolver=resolver_returning(PUBLIC_V4)
        )
    assert excinfo.value.reason == "scheme_not_https"


def test_credentials_in_the_url_are_refused() -> None:
    """A URL the operator cannot see the host of is not a URL we can allowlist."""
    with pytest.raises(BlockedTarget) as excinfo:
        validate_webhook_url(
            "https://user:pass@hooks.example.com/alerts",  # pragma: allowlist secret
            allowlist=("hooks.example.com",),
            resolver=resolver_returning(PUBLIC_V4),
        )
    assert excinfo.value.reason == "credentials_in_url"


def test_a_fragment_is_refused() -> None:
    with pytest.raises(BlockedTarget) as excinfo:
        validate_webhook_url(
            "https://hooks.example.com/alerts#x",
            allowlist=("hooks.example.com",),
            resolver=resolver_returning(PUBLIC_V4),
        )
    assert excinfo.value.reason == "fragment_in_url"


def test_a_host_that_is_not_allowlisted_is_refused_without_resolving_it() -> None:
    def boom(host: str, port: int) -> Sequence[str]:
        raise AssertionError("a refused host must not be resolved")

    with pytest.raises(BlockedTarget) as excinfo:
        validate_webhook_url(
            "https://attacker.test/alerts", allowlist=("hooks.example.com",), resolver=boom
        )
    assert excinfo.value.reason == "host_not_allowlisted"


def test_a_name_that_does_not_resolve_is_refused() -> None:
    with pytest.raises(BlockedTarget) as excinfo:
        validate_webhook_url(
            "https://hooks.example.com/alerts",
            allowlist=("hooks.example.com",),
            resolver=raising_resolver(),
        )
    assert excinfo.value.reason == "unresolvable_host"


@pytest.mark.parametrize(("address", "reason"), REFUSED_ADDRESSES)
def test_every_refused_address_class_is_refused(address: str, reason: str) -> None:
    with pytest.raises(BlockedTarget) as excinfo:
        validate_webhook_url(
            "https://hooks.example.com/alerts",
            allowlist=("hooks.example.com",),
            resolver=resolver_returning(address),
        )
    assert excinfo.value.reason == "forbidden_address"
    assert excinfo.value.detail == reason


def test_ipv4_multicast_is_not_treated_as_globally_routable() -> None:
    """CPython calls 224/4 global; a webhook may not be sent to it.

    Pinned separately from the table above because it is the one address class a
    straightforward ``is_global`` check gets wrong, and a regression here would
    otherwise look like a deliberate policy choice.
    """
    assert security_verdict_of_address("224.0.0.1") == (False, "multicast")
    assert security_verdict_of_address("239.255.255.250")[0] is False


@pytest.mark.parametrize(("plain", "embedded"), EMBEDDED_PAIRS)
def test_an_embedded_ipv4_address_is_judged_by_the_address_it_embeds(
    plain: str, embedded: str
) -> None:
    """The rule rather than the rows: embedding must not move a verdict.

    A property, because the table above can only fail for the forms someone
    thought to list, and because this is the assertion that fails on *both*
    interpreters: before the fix, 3.11.2 accepted ``::224.0.0.1`` outright and
    3.11.11+ refused it, while 3.12.4 accepted ``::ffff:224.0.0.1`` -- so no
    single row expectation would have held on every interpreter. The one that
    did fail in CI, ``::ffff:127.0.0.1`` reading ``private`` locally and
    ``loopback`` there, is how the defect was found.
    """
    assert security_verdict_of_address(embedded) == security_verdict_of_address(plain)


def test_something_that_is_not_an_address_is_refused() -> None:
    """The verdict function is total: a resolver cannot return a value it accepts."""
    assert security_verdict_of_address("not-an-address") == (False, "not_an_address")


def test_a_missing_host_and_a_bad_port_are_refused_before_dns() -> None:
    def boom(host: str, port: int) -> Sequence[str]:
        raise AssertionError("an inadmissible URL must not be resolved")

    with pytest.raises(BlockedTarget) as missing:
        validate_webhook_url("https:///alerts", allowlist=("hooks.example.com",), resolver=boom)
    assert missing.value.reason == "missing_host"
    with pytest.raises(BlockedTarget) as port:
        validate_webhook_url(
            "https://hooks.example.com:99999/alerts",
            allowlist=("hooks.example.com",),
            resolver=boom,
        )
    assert port.value.reason == "invalid_port"


def test_a_resolver_that_answers_with_nothing_is_refused() -> None:
    """Resolving to no addresses is not a pass."""
    with pytest.raises(BlockedTarget) as excinfo:
        validate_webhook_url(
            "https://hooks.example.com/alerts",
            allowlist=("hooks.example.com",),
            resolver=lambda host, port: [],
        )
    assert excinfo.value.reason == "unresolvable_host"


def test_each_resolved_address_reports_its_socket_family() -> None:
    """A transport has to pick a family; guessing from a string is how it picks wrong."""
    validated = validate_webhook_url(
        "https://hooks.example.com/alerts",
        allowlist=("hooks.example.com",),
        resolver=resolver_returning(PUBLIC_V4, PUBLIC_V6),
    )
    assert [item.family for item in validated.addresses] == [4, 6]


def test_the_documentation_range_is_refused() -> None:
    """192.0.2.0/24 is reserved, not a destination."""
    with pytest.raises(BlockedTarget) as excinfo:
        validate_webhook_url(
            "https://hooks.example.com/alerts",
            allowlist=("hooks.example.com",),
            resolver=resolver_returning("192.0.2.10"),
        )
    assert excinfo.value.reason == "forbidden_address"


def test_one_refused_address_refuses_the_whole_target() -> None:
    """Split-horizon DNS/rebinding: a permitted answer does not excuse the rest."""
    with pytest.raises(BlockedTarget) as excinfo:
        validate_webhook_url(
            "https://hooks.example.com/alerts",
            allowlist=("hooks.example.com",),
            resolver=resolver_returning(PUBLIC_V4, "10.0.0.5"),
        )
    assert excinfo.value.detail == "private"


def test_the_hostname_is_normalised_case_and_trailing_dot() -> None:
    validated = validate_webhook_url(
        "https://Hooks.Example.COM./alerts",
        allowlist=("hooks.example.com",),
        resolver=resolver_returning(PUBLIC_V4),
    )
    assert validated.host == "hooks.example.com"


# --- secret storage ----------------------------------------------------------


def test_a_sealed_secret_round_trips(vault: SecretVault) -> None:
    assert vault.open(vault.seal(SIGNING_SECRET)) == SIGNING_SECRET


def test_sealing_is_not_deterministic(vault: SecretVault) -> None:
    """Two seals of one secret differ, so a store leak is not a lookup table."""
    first, second = vault.seal(SIGNING_SECRET), vault.seal(SIGNING_SECRET)
    assert first != second
    assert vault.open(first) == vault.open(second) == SIGNING_SECRET


def test_a_short_application_key_is_refused() -> None:
    with pytest.raises(ValueError):
        SecretVault("too-short")


def test_a_rotated_application_key_cannot_open_old_secrets(vault: SecretVault) -> None:
    token = vault.seal(SIGNING_SECRET)
    with pytest.raises(SecretUnreadable):
        SecretVault("a" * 48).open(token)


def test_an_edited_sealed_secret_is_unreadable(vault: SecretVault) -> None:
    token = vault.seal(SIGNING_SECRET)
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(SecretUnreadable):
        vault.open(tampered)


def test_generated_secrets_are_long_and_unique() -> None:
    generated = {SecretVault.generate_secret() for _ in range(50)}
    assert len(generated) == 50
    assert all(len(secret) >= MIN_SECRET_BYTES for secret in generated)
    secret = SecretVault.generate_secret()
    decoded = base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4))
    assert len(decoded) == MIN_SECRET_BYTES


# --- the floor (FR-21) -------------------------------------------------------


@pytest.mark.parametrize(
    ("floor", "severity", "expected"),
    [
        ("high", "critical", True),
        ("high", "high", True),
        ("high", "medium", False),
        ("critical", "high", False),
        ("critical", "critical", True),
        ("info", "info", True),
    ],
)
def test_the_severity_floor_is_inclusive(
    vault: SecretVault, floor: str, severity: str, expected: bool
) -> None:
    subject = target(vault, severity_floor=Severity(floor))
    assert subject.receives(Severity(severity)) is expected


def test_an_inactive_target_receives_nothing(vault: SecretVault) -> None:
    subject = target(vault, active=False)
    assert subject.receives(Severity.critical) is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": " "},
        {"url": ""},
        {"secret_token": ""},
        {"created_at": datetime(2026, 3, 15, 10, 0, 0)},
    ],
)
def test_a_target_that_cannot_be_delivered_to_is_refused(
    vault: SecretVault, kwargs: dict[str, Any]
) -> None:
    base: dict[str, Any] = {
        "id": "wh_1",
        "url": "https://hooks.example.com/alerts",
        "description": None,
        "severity_floor": Severity.high,
        "secret_token": seal(vault),
        "created_at": AT,
    }
    with pytest.raises(ValueError):
        WebhookTarget(**{**base, **kwargs})


# --- the signature scheme ----------------------------------------------------


def test_a_receiver_can_verify_the_signature_with_hmac_alone() -> None:
    """The acceptance criterion, checked the way a receiver checks it.

    No call into :mod:`app.services.webhook_delivery` builds the expected digest:
    the receiver's own three lines of ``hmac`` are the specification, and the
    header the sender produced must satisfy them.
    """
    body = event_body({"b": 2, "a": 1})
    header = sign_body(SIGNING_SECRET, body, timestamp=1_700_000_000)
    match = re.fullmatch(r"t=(\d+),v1=([0-9a-f]{64})", header)
    assert match is not None
    timestamp = match.group(1).encode()
    expected = hmac.new(
        SIGNING_SECRET.encode(), timestamp + b"." + body, hashlib.sha256
    ).hexdigest()
    assert match.group(2) == expected


def test_the_signed_bytes_are_the_sent_bytes() -> None:
    """The signature covers the wire bytes, not a re-serialisation of them."""
    document = {"event": EVENT_NAME, "alert": {"severity": "high", "id": 1}}
    body = event_body(document)
    assert body == json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    assert json.loads(body) == document


def test_the_event_body_does_not_depend_on_key_order() -> None:
    assert event_body({"a": 1, "b": 2}) == event_body({"b": 2, "a": 1})


def test_a_fresh_signature_verifies() -> None:
    body = b'{"event":"alert.created"}'
    timestamp = 1_700_000_000
    check = verify_signature(
        SIGNING_SECRET,
        body,
        sign_body(SIGNING_SECRET, body, timestamp=timestamp),
        now=datetime.fromtimestamp(timestamp + 5, UTC),
    )
    assert check.valid and check.reason == "ok"


def test_a_tampered_body_does_not_verify() -> None:
    timestamp = 1_700_000_000
    header = sign_body(SIGNING_SECRET, b'{"severity":"low"}', timestamp=timestamp)
    check = verify_signature(
        SIGNING_SECRET,
        b'{"severity":"critical"}',
        header,
        now=datetime.fromtimestamp(timestamp, UTC),
    )
    assert not check.valid and check.reason == "digest_mismatch"


def test_a_body_signed_with_another_secret_does_not_verify() -> None:
    body = b"{}"
    timestamp = 1_700_000_000
    check = verify_signature(
        "another-secret",
        body,
        sign_body(SIGNING_SECRET, body, timestamp=timestamp),
        now=datetime.fromtimestamp(timestamp, UTC),
    )
    assert not check.valid and check.reason == "digest_mismatch"


def test_a_refreshed_timestamp_over_an_old_body_does_not_verify() -> None:
    """The timestamp is inside the MAC, so it cannot be swapped for a fresh one."""
    body = b'{"old":true}'
    header = sign_body(SIGNING_SECRET, body, timestamp=1_700_000_000)
    forged = re.sub(r"t=\d+", "t=1799999999", header)
    check = verify_signature(
        SIGNING_SECRET, body, forged, now=datetime.fromtimestamp(1_799_999_999, UTC)
    )
    assert not check.valid and check.reason == "digest_mismatch"


def test_an_old_signature_is_out_of_the_replay_window() -> None:
    body = b"{}"
    header = sign_body(SIGNING_SECRET, body, timestamp=1_700_000_000)
    check = verify_signature(
        SIGNING_SECRET, body, header, now=datetime.fromtimestamp(1_700_000_000 + 3600, UTC)
    )
    assert not check.valid and check.reason == "timestamp_out_of_window"


def test_a_future_signature_is_also_out_of_the_window() -> None:
    body = b"{}"
    header = sign_body(SIGNING_SECRET, body, timestamp=1_700_003_600)
    check = verify_signature(
        SIGNING_SECRET, body, header, now=datetime.fromtimestamp(1_700_000_000, UTC)
    )
    assert not check.valid and check.reason == "timestamp_out_of_window"


@pytest.mark.parametrize("header", [None, ""])
def test_a_missing_signature_header_is_reported_not_raised(header: str | None) -> None:
    check = verify_signature(SIGNING_SECRET, b"{}", header, now=AT)
    assert not check.valid and check.reason == "missing_header"


@pytest.mark.parametrize(
    "header",
    [
        "v1=abc",
        "t=notanumber,v1=abc",
        "garbage",
        "t=1700000000",
        "t=1700000000,v1=abc,sha512=def",
    ],
)
def test_a_malformed_signature_header_is_reported_not_raised(header: str) -> None:
    check = verify_signature(SIGNING_SECRET, b"{}", header, now=AT)
    assert not check.valid and check.reason in {"malformed_header", "unsupported_version"}


def test_an_unknown_signature_version_is_refused() -> None:
    """Refusing an unimplemented version is what stops a downgrade."""
    with pytest.raises(ValueError):
        parse_signature_header("t=1700000000,v2=abc")


def test_the_event_document_carries_the_alert_and_a_delivery_id() -> None:
    document = alert_event(notification(), delivery_id="d-1", at=AT)
    assert document["event"] == EVENT_NAME
    assert document["delivery"] == "d-1"
    assert document["sent_at"] == AT.isoformat()
    assert document["alert"]["severity"] == "high"  # type: ignore[index]


def test_the_event_document_does_not_carry_a_stream_sequence() -> None:
    """A receiver keyed on a per-process stream position would be keyed on sand."""
    assert "sequence" not in alert_event(notification(), delivery_id="d-1", at=AT)


# --- retry policy ------------------------------------------------------------


def test_the_backoff_grows_and_then_caps() -> None:
    policy = RetryPolicy(max_attempts=7, base_seconds=1.0, factor=2.0, max_seconds=8.0)
    assert policy.bounds() == (1.0, 2.0, 4.0, 8.0, 8.0, 8.0)
    assert policy.total_budget() == 31.0


def test_a_single_attempt_policy_has_no_backoff() -> None:
    policy = RetryPolicy(max_attempts=1)
    assert policy.bounds() == ()
    assert policy.delay(1) == 0.0
    assert policy.total_budget() == 0.0


def test_the_default_policy_is_bounded() -> None:
    policy = RetryPolicy()
    assert policy.max_attempts == 5
    assert policy.total_budget() == 15.0


def test_a_delay_is_never_larger_than_its_bound() -> None:
    policy = RetryPolicy(max_attempts=4, base_seconds=1.0, factor=2.0, max_seconds=4.0)
    with_full_jitter = [policy.delay(attempt, jitter=lambda: 1.0) for attempt in range(1, 5)]
    assert with_full_jitter == [0.0, 1.0, 2.0, 4.0]
    with_no_jitter = [policy.delay(attempt, jitter=lambda: 0.0) for attempt in range(1, 5)]
    assert with_no_jitter == [0.0, 0.0, 0.0, 0.0]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"base_seconds": 0.0},
        {"factor": 0.5},
        {"base_seconds": 5.0, "max_seconds": 1.0},
    ],
)
def test_an_unbounded_or_impossible_policy_is_refused(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


# --- delivery ----------------------------------------------------------------


def test_an_accepted_delivery_is_one_request(vault: SecretVault) -> None:
    transport = RecordingTransport([200])
    report = sender_for(transport, vault).deliver(target(vault), notification())
    assert report.delivered is True
    assert report.attempt_count == 1
    assert [attempt.outcome for attempt in report.attempts] == ["delivered"]
    assert len(transport.requests) == 1


def test_a_dead_endpoint_is_retried_exactly_to_the_bound(vault: SecretVault) -> None:
    """Bounded: the attempt count is the policy's, not "however many it managed"."""
    transport = RecordingTransport([500])
    report = sender_for(transport, vault, policy=RetryPolicy(max_attempts=4)).deliver(
        target(vault), notification()
    )
    assert report.delivered is False
    assert report.attempt_count == 4
    assert len(transport.requests) == 4
    assert [attempt.attempt for attempt in report.attempts] == [1, 2, 3, 4]


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 302])
def test_an_overload_status_is_retried(vault: SecretVault, status: int) -> None:
    transport = RecordingTransport([status, 200])
    report = sender_for(transport, vault).deliver(target(vault), notification())
    assert [attempt.outcome for attempt in report.attempts] == ["retry", "delivered"]


@pytest.mark.parametrize("status", [400, 401, 404, 410, 422])
def test_a_refusal_that_will_repeat_is_not_retried(vault: SecretVault, status: int) -> None:
    """A refusal that will repeat is not treated as a receiver being unwell."""
    transport = RecordingTransport([status])
    report = sender_for(transport, vault).deliver(target(vault), notification())
    assert report.attempt_count == 1
    assert report.attempts[0].outcome == "rejected"
    assert report.attempts[0].status == status


def test_a_transport_failure_is_retried_and_named(vault: SecretVault) -> None:
    transport = RecordingTransport([WebhookTransportError("connection_refused")])
    report = sender_for(transport, vault, policy=RetryPolicy(max_attempts=2)).deliver(
        target(vault), notification()
    )
    assert [attempt.outcome for attempt in report.attempts] == [
        "transport_error",
        "transport_error",
    ]
    assert report.attempts[0].reason == "connection_refused"


def test_a_timeout_is_retried_and_named(vault: SecretVault) -> None:
    transport = RecordingTransport([TimeoutError("peer took too long")])
    report = sender_for(transport, vault, policy=RetryPolicy(max_attempts=2)).deliver(
        target(vault), notification()
    )
    assert [attempt.reason for attempt in report.attempts] == ["timeout", "timeout"]


def test_every_attempt_of_one_delivery_carries_one_signature(vault: SecretVault) -> None:
    """A retry is the same event, not a new one: one timestamp, one delivery id."""
    transport = RecordingTransport([500, 500, 200])
    sender_for(transport, vault).deliver(target(vault), notification())
    signatures = {request.headers[SIGNATURE_HEADER] for request in transport.requests}
    timestamps = {request.headers[TIMESTAMP_HEADER] for request in transport.requests}
    deliveries = {request.headers[DELIVERY_HEADER] for request in transport.requests}
    bodies = {request.body for request in transport.requests}
    assert len(signatures) == len(timestamps) == len(deliveries) == len(bodies) == 1
    assert transport.requests[0].headers[EVENT_HEADER] == EVENT_NAME


def test_a_delivery_is_verifiable_from_the_wire_request(vault: SecretVault) -> None:
    """The end-to-end property: what the transport sends satisfies a receiver."""
    transport = RecordingTransport([200])
    sender_for(transport, vault).deliver(target(vault), notification())
    request = transport.requests[0]
    check = verify_signature(
        SIGNING_SECRET, request.body, request.headers[SIGNATURE_HEADER], now=datetime.now(UTC)
    )
    assert check.valid, check.reason
    assert json.loads(request.body)["alert"]["severity"] == "high"  # type: ignore[index]


def test_the_request_targets_the_pinned_address_not_the_hostname(vault: SecretVault) -> None:
    """A second resolution is a second chance to be rebound (R-55)."""
    transport = RecordingTransport([200])
    sender_for(transport, vault, resolver=resolver_returning(PUBLIC_V6)).deliver(
        target(vault), notification()
    )
    request = transport.requests[0]
    assert request.address == PUBLIC_V6
    assert request.url == "https://hooks.example.com/alerts"
    assert request.port == 443


def test_a_url_that_rebinds_to_a_private_address_is_refused_before_connecting(
    vault: SecretVault,
) -> None:
    """Registered as public, resolving private later: refuse, do not dial."""
    transport = RecordingTransport([200])
    report = sender_for(transport, vault, resolver=resolver_returning("169.254.169.254")).deliver(
        target(vault), notification()
    )
    assert transport.requests == []
    assert report.attempts[0].outcome == "blocked"
    assert report.attempts[0].reason == "forbidden_address:link_local"
    assert report.attempt_count == 1


def test_a_narrowed_allowlist_blocks_a_stored_target(vault: SecretVault) -> None:
    transport = RecordingTransport([200])
    report = sender_for(transport, vault, allowlist=("other.example.com",)).deliver(
        target(vault), notification()
    )
    assert transport.requests == []
    assert report.attempts[0].reason == "host_not_allowlisted"


def test_a_name_that_stops_resolving_is_retried_not_blocked(vault: SecretVault) -> None:
    """A resolver hiccup is a network condition; a private answer is not."""
    transport = RecordingTransport([200])
    report = sender_for(
        transport, vault, resolver=raising_resolver(), policy=RetryPolicy(max_attempts=2)
    ).deliver(target(vault), notification())
    assert transport.requests == []
    assert [attempt.outcome for attempt in report.attempts] == ["retry", "retry"]
    assert report.attempts[0].reason == "unresolvable_host"


def test_a_target_below_the_floor_is_never_signed(vault: SecretVault) -> None:
    """The vault is not opened for a delivery that will not happen."""
    opened: list[str] = []

    class WatchedVault(SecretVault):
        def open(self, token: str) -> str:
            opened.append(token)
            return super().open(token)

    watched = WatchedVault(SECRET)
    transport = RecordingTransport([200])
    report = sender_for(transport, watched).deliver(target(watched), notification("low"))
    assert report.skipped == "below_floor"
    assert report.attempt_count == 0
    assert report.delivery_id == ""
    assert transport.requests == []
    assert opened == []


def test_an_inactive_target_is_skipped(vault: SecretVault) -> None:
    transport = RecordingTransport([200])
    report = sender_for(transport, vault).deliver(
        target(vault, active=False), notification("critical")
    )
    assert report.skipped == "inactive"
    assert transport.requests == []


def test_an_unknown_severity_is_reported_rather_than_guessed(vault: SecretVault) -> None:
    transport = RecordingTransport([200])
    report = sender_for(transport, vault).deliver(target(vault), notification("catastrophic"))
    assert report.skipped == "unknown_severity"
    assert transport.requests == []


def test_a_sealed_secret_that_cannot_be_opened_stops_the_delivery(vault: SecretVault) -> None:
    """No retry makes a rotated key work; the failure must not look like a peer's."""
    with pytest.raises(SecretUnreadable):
        sender_for(RecordingTransport([200]), SecretVault("z" * 48)).deliver(
            target(vault), notification()
        )


def test_the_log_records_each_attempt_and_the_outcome_without_content(
    vault: SecretVault,
) -> None:
    """R-58 and R-54: a log line names the target, never the URL, the note or the alert.

    The target's URL carries a token and its description names an on-call tier;
    both are identifying, and neither belongs in a log that a wider set of people
    can read than can read the webhook configuration.
    """
    records: list[Mapping[str, object]] = []
    transport = RecordingTransport([500, 500, 200])
    watched = target(
        vault,
        url="https://hooks.example.com/alerts/3f9c1d2e-secret-path",
        description="PagerDuty tier-2, contact soc@corp",
    )
    sender_for(transport, vault, log=records.append).deliver(watched, notification())

    assert [record["event"] for record in records] == [
        "webhook.attempt",
        "webhook.attempt",
        "webhook.attempt",
        "webhook.delivery",
    ]
    assert records[-1]["attempts"] == 3
    assert records[-1]["delivered"] is True
    blob = repr(records)
    assert "hooks.example.com" not in blob  # no URL: it may carry a token
    assert "3f9c1d2e" not in blob
    assert "pagerduty" not in blob.lower()
    assert "soc@corp" not in blob
    assert SIGNING_SECRET not in blob
    assert "reconnaissance" not in blob.lower()  # no alert content (R-58)
    assert "0.91" not in blob


def test_delivery_reports_are_json_serialisable() -> None:
    """The report is what a future delivery log persists (T-311's own log line)."""
    report = DeliveryReport(
        delivery_id="d-1",
        target_id="wh_1",
        delivered=False,
        attempts=(),
        skipped="below_floor",
    )
    assert json.loads(json.dumps(asdict(report)))["skipped"] == "below_floor"


def test_dispatch_fans_out_and_reports_every_target(vault: SecretVault) -> None:
    transport = RecordingTransport([200])
    sender = sender_for(transport, vault)
    targets = (
        target(vault, id="wh_1", severity_floor=Severity.high),
        target(
            vault, id="wh_2", severity_floor=Severity.critical, url="https://hooks2.example.com/x"
        ),
        target(vault, id="wh_3", active=False),
    )
    reports = dispatch(notification("high"), targets, sender)
    assert [(report.target_id, report.delivered, report.skipped) for report in reports] == [
        ("wh_1", True, None),
        ("wh_2", False, "below_floor"),
        ("wh_3", False, "inactive"),
    ]
    assert len(transport.requests) == 1


def test_dispatch_with_no_targets_is_empty(vault: SecretVault) -> None:
    assert dispatch(notification(), (), sender_for(RecordingTransport([200]), vault)) == ()


def test_a_delivery_id_is_unique_within_one_clock_tick(vault: SecretVault) -> None:
    """Two deliveries in the same second must not share an id: receivers dedupe on it."""
    transport = RecordingTransport([200])
    sender = sender_for(transport, vault)
    for _ in range(25):
        sender.deliver(target(vault), notification())
    ids = {request.headers[DELIVERY_HEADER] for request in transport.requests}
    assert len(ids) == 25


# --- the HTTP surface --------------------------------------------------------


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def settings() -> Settings:
    """Settings with an allowlist, so the endpoints have something to permit."""
    return Settings(
        env="test",
        service_name="aegis-backend-test",
        secret_key=APP_SECRET,
        log_level="WARNING",
        webhook_allowlist="hooks.example.com,*.corp.example.com",
    )


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    built = create_app(settings)
    built.state.token_service = auth
    # The DNS seam: whether a URL is public is the test's decision, not the
    # sandbox's (there is no network here, and a name that resolves on one
    # machine and not another is not a test).
    built.state.webhook_resolver = resolver_returning(PUBLIC_V4)
    with TestClient(built) as test_client:
        yield test_client


def auth_headers(auth: TokenService, role: str = "responder") -> dict[str, str]:
    """An Authorization header for one role."""
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def register(
    client: TestClient,
    auth: TokenService,
    url: str = "https://hooks.example.com/x",
    role: str = "responder",
) -> Any:  # noqa: ANN401 -- the response, asserted field by field at each use
    """Register a target through the API, as one role, and return the response."""
    return client.post("/api/v1/webhooks", json={"url": url}, headers=auth_headers(auth, role))


def test_the_production_resolver_is_the_real_one() -> None:
    """The injected seam must default to DNS, or R-55 checks nothing."""
    from app.services.webhook_targets import resolve_host

    fresh = create_app(Settings(env="test", service_name="t", secret_key=APP_SECRET))
    assert fresh.state.webhook_resolver is resolve_host


def test_registering_a_target_returns_its_secret_once(
    client: TestClient, auth: TokenService
) -> None:
    response = register(client, auth)
    assert response.status_code == 201
    body = response.json()
    assert body["secret"]
    assert body["severity_floor"] == "high"
    assert body["active"] is True
    assert response.headers["Location"] == f"/api/v1/webhooks/{body['id']}"
    assert body["url"] == "https://hooks.example.com/x"


def test_the_returned_secret_is_the_stored_one(client: TestClient, auth: TokenService) -> None:
    """The response is the only place the plaintext appears -- and it is real."""
    secret = register(client, auth).json()["secret"]
    stored = client.app.state.webhook_store.list()  # type: ignore[attr-defined]
    assert len(stored) == 1
    assert stored[0].secret_token != secret
    assert client.app.state.secret_vault.open(stored[0].secret_token) == secret  # type: ignore[attr-defined]


def test_reading_configuration_never_returns_a_secret(
    client: TestClient, auth: TokenService
) -> None:
    register(client, auth)
    listed = client.get("/api/v1/webhooks", headers=auth_headers(auth))
    assert listed.status_code == 200
    assert "secret" not in listed.text
    assert "secret_token" not in listed.text
    assert len(listed.json()["items"]) == 1


def test_a_registered_target_can_be_deleted(client: TestClient, auth: TokenService) -> None:
    created = register(client, auth).json()
    deleted = client.delete(f"/api/v1/webhooks/{created['id']}", headers=auth_headers(auth))
    assert deleted.status_code == 204
    assert client.get("/api/v1/webhooks", headers=auth_headers(auth)).json()["items"] == []


def test_deleting_an_unknown_target_is_404(client: TestClient, auth: TokenService) -> None:
    response = client.delete("/api/v1/webhooks/wh_404", headers=auth_headers(auth))
    assert response.status_code == 404


def test_registering_the_same_url_twice_is_409(client: TestClient, auth: TokenService) -> None:
    """Two targets on one URL deliver every alert twice."""
    register(client, auth)
    duplicate = register(client, auth)
    assert duplicate.status_code == 409


def test_a_custom_severity_floor_is_stored(client: TestClient, auth: TokenService) -> None:
    response = client.post(
        "/api/v1/webhooks",
        json={"url": "https://hooks.example.com/x", "severity_floor": "critical"},
        headers=auth_headers(auth),
    )
    assert response.status_code == 201
    assert response.json()["severity_floor"] == "critical"


def test_an_unknown_severity_floor_is_refused(client: TestClient, auth: TokenService) -> None:
    response = client.post(
        "/api/v1/webhooks",
        json={"url": "https://hooks.example.com/x", "severity_floor": "urgent"},
        headers=auth_headers(auth),
    )
    assert response.status_code == 400
    assert "critical" in response.json()["detail"]


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://hooks.example.com/x", "scheme_not_https"),
        # the credentials are the test input, not a credential
        ("https://user:pw@hooks.example.com/x", "credentials_in_url"),  # pragma: allowlist secret
        ("https://hooks.example.com/x#f", "fragment_in_url"),
        ("https://attacker.test/x", "host_not_allowlisted"),
    ],
)
def test_an_inadmissible_url_is_refused_when_registered(
    client: TestClient, auth: TokenService, url: str, reason: str
) -> None:
    response = register(client, auth, url)
    assert response.status_code == 400
    assert reason in response.json()["detail"]
    assert url not in response.text


def test_a_private_address_is_refused_when_registered(
    client: TestClient, auth: TokenService
) -> None:
    """The SSRF control's acceptance case, through the real endpoint."""
    client.app.state.webhook_resolver = resolver_returning("10.0.0.5")  # type: ignore[attr-defined]
    response = register(client, auth)
    assert response.status_code == 400
    assert "forbidden_address" in response.json()["detail"]
    assert "private" in response.json()["detail"]
    assert client.app.state.webhook_store.list() == ()  # type: ignore[attr-defined]


def test_the_link_local_metadata_address_is_refused_when_registered(
    client: TestClient, auth: TokenService
) -> None:
    """169.254.169.254 is the credential endpoint, and the headline SSRF case."""
    client.app.state.webhook_resolver = resolver_returning("169.254.169.254")  # type: ignore[attr-defined]
    response = register(client, auth)
    assert response.status_code == 400
    assert "link_local" in response.json()["detail"]


def test_an_unresolvable_host_is_refused_when_registered(
    client: TestClient, auth: TokenService
) -> None:
    client.app.state.webhook_resolver = raising_resolver()  # type: ignore[attr-defined]
    response = register(client, auth)
    assert response.status_code == 400
    assert "unresolvable_host" in response.json()["detail"]


def test_a_wildcard_allowlist_entry_permits_one_label_beneath(
    client: TestClient, auth: TokenService
) -> None:
    assert register(client, auth, "https://hooks.corp.example.com/x").status_code == 201
    assert register(client, auth, "https://deep.hooks.corp.example.com/x").status_code == 400


def test_webhook_configuration_needs_the_capability(client: TestClient, auth: TokenService) -> None:
    """R-53: responder and above; and reading is as sensitive as writing."""
    for role, allowed in (
        ("responder", True),
        ("admin", True),
        ("analyst", False),
        ("viewer", False),
    ):
        write = register(client, auth, f"https://hooks.example.com/{role}", role)
        read = client.get("/api/v1/webhooks", headers=auth_headers(auth, role))
        if allowed:
            assert (write.status_code, read.status_code) == (201, 200), role
        else:
            assert (write.status_code, read.status_code) == (403, 403), role


def test_webhook_configuration_is_closed_to_anonymous_callers(client: TestClient) -> None:
    assert (
        client.post("/api/v1/webhooks", json={"url": "https://hooks.example.com/x"}).status_code
        == 401
    )
    assert client.get("/api/v1/webhooks").status_code == 401
    assert client.delete("/api/v1/webhooks/wh_1").status_code == 401


def test_an_empty_allowlist_refuses_everything(client: TestClient, auth: TokenService) -> None:
    """The default configuration is fail-closed (R-55)."""
    client.app.state.webhook_allowlist = ()  # type: ignore[attr-defined]
    response = register(client, auth)
    assert response.status_code == 400
    assert "host_not_allowlisted" in response.json()["detail"]


def test_the_store_adds_lists_and_removes(vault: SecretVault) -> None:
    store = InMemoryWebhookStore()
    first = target(vault, id="wh_1")
    store.add(first)
    store.add(target(vault, id="wh_2", url="https://hooks2.example.com/x"))
    assert [item.id for item in store.list()] == ["wh_1", "wh_2"]
    assert store.get("wh_2") is not None
    assert store.remove("wh_1") is True
    assert store.remove("wh_1") is False
    assert [item.id for item in store.list()] == ["wh_2"]
    store.add(target(vault, id="wh_2", url="https://hooks.example.com/replaced"))
    assert [item.url for item in store.list()] == ["https://hooks.example.com/replaced"]


def test_a_timestamp_header_matches_the_signed_timestamp(vault: SecretVault) -> None:
    """A receiver reading either header must see the same instant."""
    transport = RecordingTransport([200])
    sender_for(transport, vault).deliver(target(vault), notification())
    request = transport.requests[0]
    parsed = parse_signature_header(request.headers[SIGNATURE_HEADER])
    assert str(parsed.timestamp) == request.headers[TIMESTAMP_HEADER]


def test_the_sender_refuses_a_non_positive_timeout(vault: SecretVault) -> None:
    with pytest.raises(ValueError):
        WebhookSender(RecordingTransport([200]), vault, ("hooks.example.com",), timeout=0)


def test_a_delivery_report_carries_the_time_it_waited(vault: SecretVault) -> None:
    """The wait is reported, so backoff is observable without a stopwatch."""
    transport = RecordingTransport([500, 200])
    policy = RetryPolicy(max_attempts=3, base_seconds=2.0, factor=2.0, max_seconds=8.0)
    report = sender_for(transport, vault, policy=policy).deliver(target(vault), notification())
    assert [attempt.delay_before for attempt in report.attempts] == [0.0, 2.0]
    assert report.waited_seconds == 2.0


def test_the_replay_window_and_the_retry_budget_agree(vault: SecretVault) -> None:
    """A retry that outlives the window would be refused by every receiver.

    This is the arithmetic that ties the two bounds together; if the policy
    grows past the window, one of the two has to be reconsidered deliberately.
    """
    from app.services.webhook_delivery import REPLAY_WINDOW_SECONDS

    assert RetryPolicy().total_budget() < REPLAY_WINDOW_SECONDS


def test_the_window_tolerates_clock_skew_in_both_directions() -> None:
    body = b"{}"
    timestamp = int(AT.timestamp())
    header = sign_body(SIGNING_SECRET, body, timestamp=timestamp)
    for drift in (-30, 0, 30):
        check = verify_signature(SIGNING_SECRET, body, header, now=AT + timedelta(seconds=drift))
        assert check.valid, drift
