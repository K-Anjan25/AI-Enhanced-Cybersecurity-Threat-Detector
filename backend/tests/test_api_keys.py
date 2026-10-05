"""T-313: API keys -- scopes, keyed hashing, one-time secret, immediate revocation (FR-44).

The acceptance criterion is three sentences: the secret is returned exactly once,
only a prefix is stored, and revoked keys are rejected immediately. Each one is
asserted here in the way that cannot be satisfied by accident.

*Exposed once* is asserted as an absence: :class:`ApiKeyOut` has no secret field
(so no listing can carry one), the stored record has no secret field, issuing
twice produces different secrets, and the plaintext does not appear anywhere in
the trail, in the store, or in the listing after the one response that carries it.

*Only a prefix is stored* is asserted against the storage itself: the digest is
what the column holds, the digest does not contain the secret half, and the only
derivable display value is ``aegis_sk_<id>_``.

*Revoked immediately* is asserted through HTTP: the next request that presents a
revoked key is a 401, with no cache in between -- verification reads the store
every time by construction, and the test proves the behaviour rather than the
intention.

The authorisation half matters as much as the crypto half, so the scope table is
checked against R-53's role matrix: **a key can never hold authority that the
least-privileged role permitted on that route also lacks.** A key is a machine
credential, and the failure mode of a sloppy scope map is a robot with an
administrator's reach.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.auth.api_keys import (
    API_KEY_PREFIX,
    DEFAULT_TOUCH_INTERVAL_SECONDS,
    KEY_SECRET_BYTES,
    ApiKeyRecord,
    ApiKeyStore,
    InMemoryApiKeyStore,
    InvalidKeyFormat,
    KeyDigest,
    Scope,
    api_key_insert,
    api_key_revoke,
    api_key_select,
    api_key_touch,
    format_key,
    generate_secret,
    issue_key,
    looks_like_key,
    parse_key,
    revoke_key,
    scopes_from_names,
    verify_key,
)
from app.auth.rbac import (
    API_KEY_ROUTES,
    ROLE_CAPABILITIES,
    ROUTE_MATRIX,
    SCOPE_CAPABILITIES,
    Capability,
    PrincipalKind,
    Role,
    capabilities_of_principal,
)
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.main import create_app
from app.schemas.api_key import ApiKeyIssuedOut, ApiKeyListOut, ApiKeyOut, ScopeOut
from app.services.audit_log import AuditAction, InMemoryAuditTrail
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

SECRET = "s" * 48
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
AT = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)
LATER = AT + timedelta(hours=1)

FLOW = {
    "schema_version": "flow@1",
    "timestamp": "2026-10-05T12:00:00Z",
    "src_ip": "10.0.0.1",
    "dst_ip": "10.0.0.2",
    "src_port": 4444,
    "dst_port": 443,
    "protocol": "tcp",
    "direction": "outbound",
    "packets": 12,
    "src_packets": 7,
    "dst_packets": 5,
    "src_bytes": 900,
    "dst_bytes": 400,
    "duration": 1.5,
}

#: Method names that would be a way to destroy or rewrite a key row. There is
#: deliberately no delete: revocation is a column, and the row is the record.
DESTRUCTIVE_WORDS = {"delete", "remove", "purge", "truncate", "drop", "destroy"}


# --- fixtures ----------------------------------------------------------------


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


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    built = create_app(settings)
    built.state.token_service = auth
    with TestClient(built) as test_client:
        yield test_client


@pytest.fixture
def digest() -> KeyDigest:
    return KeyDigest(APP_SECRET)


@pytest.fixture
def store() -> InMemoryApiKeyStore:
    return InMemoryApiKeyStore()


def headers(auth: TokenService, role: str = "admin") -> dict[str, str]:
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def trail_of(client: TestClient) -> InMemoryAuditTrail:
    trail: InMemoryAuditTrail = client.app.state.audit_trail  # type: ignore[attr-defined]
    return trail


def all_entries(client: TestClient) -> list[Any]:
    now = datetime.now(UTC)
    entries = trail_of(client).entries(start=now - timedelta(hours=1), end=now + timedelta(hours=1))
    return list(entries)


def issued(
    client: TestClient, *, scopes: list[str] | None = None, name: str = "collector-1"
) -> dict:
    """Issue a key through the API as an admin and return the response body."""
    response = client.post(
        "/api/v1/keys",
        json={"name": name, "scopes": scopes if scopes is not None else ["ingest:write"]},
        headers=headers(client.app.state.token_service, "admin"),  # type: ignore[attr-defined]
    )
    assert response.status_code == 201, response.text
    return response.json()


def key_headers(secret: str) -> dict[str, str]:
    return {"X-API-Key": secret}


def window() -> dict[str, str]:
    """The alert list's required window (R-34), wide enough to cover a test run."""
    now = datetime.now(UTC)
    return {
        "start": (now - timedelta(hours=1)).isoformat(),
        "end": (now + timedelta(hours=1)).isoformat(),
    }


# --- the key format ----------------------------------------------------------


def test_a_key_is_the_public_id_then_a_secret(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    issued_key = issue_key(
        store,
        digest,
        name="collector-1",
        owner="admin@corp",
        scopes=frozenset({Scope.ingest_write}),
        at=AT,
    )
    assert issued_key.secret.startswith(f"{API_KEY_PREFIX}{issued_key.record.id}_")
    parsed = parse_key(issued_key.secret)
    assert parsed.key_id == issued_key.record.id
    assert parsed.secret == issued_key.secret.split("_", 3)[3]


def test_the_prefix_is_the_public_half_and_nothing_else(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    issued_key = issue_key(
        store,
        digest,
        name="c",
        owner="o@corp",
        scopes=frozenset({Scope.ingest_write}),
        at=AT,
    )
    secret_half = issued_key.secret.split("_", 3)[3]
    assert issued_key.record.prefix == f"{API_KEY_PREFIX}{issued_key.record.id}_"
    assert secret_half not in issued_key.record.prefix


@pytest.mark.parametrize(
    "presented",
    [
        "",
        "   ",
        "aegis_sk_",
        "aegis_sk_1",
        "aegis_sk_1_",
        "aegis_sk_x_abc",
        "aegis_sk__abc",
        "aegis_sk_1_abc.def",  # base64 punctuation outside the alphabet
        "sk_1_abc",
        "aegis_sk_1_abc def",
        "aegis_sk_0000000000000000000000_abc",  # id wider than bigint
        "eyJhbGciOiJIUzI1NiJ9.token",  # a JWT is not a key
    ],
)
def test_a_string_that_is_not_a_key_is_refused_not_guessed(presented: str) -> None:
    with pytest.raises(InvalidKeyFormat):
        parse_key(presented)
    assert looks_like_key(presented) is False


def test_parsing_tolerates_surrounding_whitespace() -> None:
    """A header value with a stray newline is a clipboard artefact, not a wrong key."""
    assert parse_key("  aegis_sk_4_abc  ").key_id == 4
    assert looks_like_key("\taegis_sk_4_abc\n") is True


def test_parse_and_looks_like_key_agree(digest: KeyDigest, store: InMemoryApiKeyStore) -> None:
    """Two answers to "is this a key" would be a way to route a credential wrong."""
    real = issue_key(
        store,
        digest,
        name="c",
        owner="o@corp",
        scopes=frozenset({Scope.ingest_write}),
        at=AT,
    ).secret
    for candidate in (real, "aegis_sk_1_", "nope", "", "aegis_sk_2_" + "a" * 43):
        assert looks_like_key(candidate) is (parse_ok(candidate))


def parse_ok(candidate: str) -> bool:
    """Whether :func:`parse_key` accepts a string, without propagating."""
    try:
        parse_key(candidate)
    except InvalidKeyFormat:
        return False
    return True


def test_format_key_refuses_an_id_that_is_not_a_row_id() -> None:
    with pytest.raises(ValueError, match="positive"):
        format_key(0, "abc")
    with pytest.raises(ValueError, match="secret half"):
        format_key(1, "")


def test_generated_secrets_are_long_enough_and_never_repeat() -> None:
    """256 bits from the OS entropy pool, not a sequence and not a uuid4."""
    drawn = {generate_secret() for _ in range(200)}
    assert len(drawn) == 200
    assert all(len(secret) >= 32 for secret in drawn)
    assert KEY_SECRET_BYTES == 32


# --- the digest: what is actually stored -------------------------------------


def test_the_stored_digest_is_64_lowercase_hex(digest: KeyDigest) -> None:
    """Exactly the width of ``api_keys.key_hash``: the schema needs no migration."""
    value = digest.digest("aegis_sk_1_abc")
    assert len(value) == 64
    assert value == value.lower()
    assert all(char in "0123456789abcdef" for char in value)


def test_the_digest_is_keyed_not_a_bare_hash(digest: KeyDigest) -> None:
    """HMAC under a derived key, so a stolen database is not an offline oracle."""
    key = "aegis_sk_1_" + "a" * 43
    assert digest.digest(key) != hashlib.sha256(key.encode()).hexdigest()


def test_two_deployments_do_not_share_digests() -> None:
    """A digest key is per-deployment.

    It is derived from AEGIS_SECRET_KEY, so a database restored into another
    environment does not authenticate the machines of the old one.
    """
    key = "aegis_sk_1_" + "a" * 43
    assert KeyDigest(APP_SECRET).digest(key) != KeyDigest("x" * 40).digest(key)


def test_a_short_application_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        KeyDigest("too-short")


def test_a_missing_row_is_compared_against_a_dummy(digest: KeyDigest) -> None:
    """No short-circuit: the digest is computed even when there is nothing to match.

    Timing is not measured here -- a test that asserted nanoseconds would be flaky
    -- so what is asserted is the work itself: :meth:`KeyDigest.matches` derives a
    digest for a row that does not exist, which is what makes "unknown id" and
    "wrong secret" the same amount of work.
    """
    from unittest.mock import patch

    real = KeyDigest.digest
    with patch.object(KeyDigest, "digest", autospec=True, side_effect=real) as spy:
        assert digest.matches("aegis_sk_9_" + "a" * 43, None) is False
    assert spy.call_count == 1


def test_the_secret_half_is_not_recoverable_from_the_record(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    """Only a prefix is stored: the record holds a digest, and the digest is one way."""
    issued_key = issue_key(
        store,
        digest,
        name="c",
        owner="o@corp",
        scopes=frozenset({Scope.ingest_write}),
        at=AT,
    )
    secret_half = issued_key.secret.split("_", 3)[3]
    stored = store.get(issued_key.record.id)
    assert stored is not None
    assert stored.digest != issued_key.secret
    assert secret_half not in stored.digest
    assert issued_key.secret not in repr(stored)
    assert "secret" not in set(ApiKeyRecord.__dataclass_fields__)


def test_the_module_offers_no_way_back_from_a_digest() -> None:
    """The absence of an inverse is the property; a function named one would fail it."""
    import app.auth.api_keys as module

    forbidden = ("reveal", "decrypt", "unhash", "recover", "plaintext", "open_key")
    names = [name for name in dir(module) if not name.startswith("__")]
    assert [name for name in names if any(word in name.lower() for word in forbidden)] == []


def test_a_key_is_a_field_of_the_creation_schema_only() -> None:
    assert "secret" in ApiKeyIssuedOut.model_fields
    assert "secret" not in ApiKeyOut.model_fields
    assert "secret" not in ApiKeyListOut.model_fields
    assert "secret" not in ScopeOut.model_fields


def test_the_issue_response_cannot_be_rebuilt_without_the_secret() -> None:
    """Frozen and extra-forbid: a response model is not a place to stash extra data."""
    with pytest.raises(Exception):  # noqa: B017 -- pydantic raises ValidationError
        ApiKeyOut(  # type: ignore[call-arg]
            id=1,
            name="c",
            prefix="aegis_sk_1_",
            owner="o@corp",
            scopes=["ingest:write"],
            created_at=AT,
            last_used_at=None,
            revoked_at=None,
            secret="aegis_sk_1_abc",  # type: ignore[call-arg]
        )


# --- verification ------------------------------------------------------------


def test_a_good_key_resolves_to_its_record(digest: KeyDigest, store: InMemoryApiKeyStore) -> None:
    issued_key = issue_key(
        store,
        digest,
        name="c",
        owner="o@corp",
        scopes=frozenset({Scope.ingest_write}),
        at=AT,
    )
    resolved = verify_key(store, digest, issued_key.secret, at=LATER)
    assert resolved is not None
    assert resolved.id == issued_key.record.id
    assert resolved.last_used_at == LATER


@pytest.mark.parametrize(
    "tamper",
    [
        lambda key: key[:-1] + ("A" if key[-1] != "A" else "B"),  # wrong secret
        lambda key: key.replace("_sk_1_", "_sk_2_", 1),  # rewritten id, same secret
        lambda key: key.replace("_sk_1_", "_sk_01_", 1),  # padded id: a different string
    ],
)
def test_a_tampered_key_never_resolves(
    digest: KeyDigest, store: InMemoryApiKeyStore, tamper: Any
) -> None:
    """The digest covers the whole presentation, so the id half is MAC-protected too."""
    issued_key = issue_key(
        store,
        digest,
        name="c",
        owner="o@corp",
        scopes=frozenset({Scope.ingest_write}),
        at=AT,
    )
    assert verify_key(store, digest, tamper(issued_key.secret), at=LATER) is None


def test_a_string_outside_the_key_format_is_not_a_bad_key_but_not_a_key(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    """A wrong public prefix is a different credential kind, not a failed attempt."""
    issued_key = issue_key(
        store, digest, name="c", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    mislabelled = issued_key.secret.replace("aegis_sk_", "aegis_sh_", 1)
    with pytest.raises(InvalidKeyFormat):
        verify_key(store, digest, mislabelled, at=LATER)


def test_a_key_that_was_never_issued_never_resolves(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    assert verify_key(store, digest, f"{API_KEY_PREFIX}77_" + "a" * 43, at=LATER) is None


def test_two_keys_do_not_verify_against_each_other(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    first = issue_key(
        store, digest, name="a", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    second = issue_key(
        store, digest, name="b", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    assert first.secret != second.secret
    assert verify_key(store, digest, first.secret, at=LATER).id != second.record.id  # type: ignore[union-attr]


def test_an_unparseable_string_raises_rather_than_returning_none(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    """The caller distinguishes "not a key" from "not a valid key" to route it."""
    with pytest.raises(InvalidKeyFormat):
        verify_key(store, digest, "not-a-key", at=LATER)


def test_verification_does_not_stamp_a_use_for_a_key_that_fails(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    """A failed attempt is not a use, and must not make one look live."""
    issued_key = issue_key(
        store, digest, name="c", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    assert verify_key(store, digest, issued_key.secret[:-1] + "Z", at=LATER) is None
    assert store.get(issued_key.record.id).last_used_at is None  # type: ignore[union-attr]


# --- revocation --------------------------------------------------------------


def test_a_revoked_key_is_refused_by_the_next_verification(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    issued_key = issue_key(
        store, digest, name="c", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    assert verify_key(store, digest, issued_key.secret, at=AT) is not None
    revoked = revoke_key(store, issued_key.record.id, at=LATER)
    assert revoked is not None and revoked.revoked_at == LATER
    assert verify_key(store, digest, issued_key.secret, at=LATER + timedelta(seconds=1)) is None


def test_revoking_twice_keeps_the_first_timestamp(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    """The timestamp records when the credential stopped working.

    A second revoke is a no-op rather than a later click: an operator asking
    when a key died gets the same answer twice.
    """
    issued_key = issue_key(
        store, digest, name="c", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    first = revoke_key(store, issued_key.record.id, at=AT)
    second = revoke_key(store, issued_key.record.id, at=LATER)
    assert first is not None and second is not None
    assert second.revoked_at == AT


def test_a_revoked_key_stays_in_the_store(store: InMemoryApiKeyStore, digest: KeyDigest) -> None:
    """Revocation is a state, not a deletion: the row answers "what existed"."""
    issued_key = issue_key(
        store, digest, name="c", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    revoke_key(store, issued_key.record.id, at=LATER)
    assert len(store.list()) == 1
    record = store.get(issued_key.record.id)
    assert record is not None and record.active is False
    assert record.grants(Scope.ingest_write) is False


def test_revoking_an_unknown_key_reports_it(store: InMemoryApiKeyStore) -> None:
    assert revoke_key(store, 404, at=AT) is None


def test_the_store_has_no_delete_path() -> None:
    """R-31's reasoning is about history, not about one table.

    A key row is the record of a credential having existed, so there is no way
    to destroy it.
    """
    protocol_names = {name for name in dir(ApiKeyStore) if not name.startswith("_")}
    store_names = {name for name in dir(InMemoryApiKeyStore) if not name.startswith("_")}
    for names in (protocol_names, store_names):
        assert not {name for name in names if name.lower() in DESTRUCTIVE_WORDS}


def module_file() -> str:
    """The api_keys source, read once for the source-level assertions."""
    import app.auth.api_keys as module

    assert module.__file__ is not None
    with open(module.__file__) as handle:
        return handle.read()


def test_the_module_contains_no_delete_statement() -> None:
    """A source-level check, because a helper that deletes would pass the dir() test."""
    source = module_file()
    text = source.lower()
    for word in DESTRUCTIVE_WORDS:
        assert f"{word}(" not in text
        assert f"{word} from api_keys" not in text


# --- the last-used stamp -----------------------------------------------------


def test_a_use_is_stamped_at_most_once_per_interval(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    """The hot row is not rewritten on every ingest request."""
    issued_key = issue_key(
        store, digest, name="c", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    verify_key(store, digest, issued_key.secret, at=AT)
    assert store.get(issued_key.record.id).last_used_at == AT  # type: ignore[union-attr]
    verify_key(store, digest, issued_key.secret, at=AT + timedelta(seconds=5))
    assert store.get(issued_key.record.id).last_used_at == AT  # type: ignore[union-attr]
    verify_key(store, digest, issued_key.secret, at=AT + timedelta(seconds=61))
    assert store.get(issued_key.record.id).last_used_at == AT + timedelta(seconds=61)  # type: ignore[union-attr]


def test_touching_an_unknown_key_reports_it(store: InMemoryApiKeyStore) -> None:
    assert store.touch(404, at=AT) is False


# --- scopes ------------------------------------------------------------------


def test_the_scope_set_is_small_and_named_noun_colon_verb() -> None:
    assert {scope.value for scope in Scope} == {"ingest:write", "alerts:read"}
    for scope in Scope:
        assert scope.value.count(":") == 1


def test_every_scope_grants_something() -> None:
    """A scope that grants nothing is a scope nobody should be offered."""
    assert set(SCOPE_CAPABILITIES) == set(Scope)
    assert all(SCOPE_CAPABILITIES[scope] for scope in Scope)


def test_scope_names_parse_case_sensitively_and_refuse_typos() -> None:
    assert scopes_from_names(["ingest:write", " alerts:read "]) == frozenset(
        {Scope.ingest_write, Scope.alerts_read}
    )
    with pytest.raises(ValueError, match="unknown scope"):
        scopes_from_names(["ingest:write", "ingest:read"])
    with pytest.raises(ValueError, match="unknown scope"):
        scopes_from_names(["INGEST:WRITE"])
    with pytest.raises(ValueError, match="unknown scope"):
        scopes_from_names([""])


def test_a_record_must_carry_at_least_one_scope() -> None:
    """An empty set would have to mean "nothing" or "everything"; both are wrong."""
    with pytest.raises(ValueError, match="at least one scope"):
        ApiKeyRecord(
            id=1,
            name="c",
            owner="o@corp",
            scopes=frozenset(),
            digest="a" * 64,
            created_at=AT,
        )


# --- the statements the persistent store will run ----------------------------

DIALECT = postgresql.dialect()


def compiled(statement: Any) -> tuple[str, Any]:
    """The SQL text and its bind parameters, both needed to see a lost bound."""
    built = statement.compile(dialect=DIALECT)
    return str(built), built.params


def sample_record(**overrides: Any) -> ApiKeyRecord:
    fields: dict[str, Any] = {
        "id": 3,
        "name": "collector-1",
        "owner": "admin@corp",
        "scopes": frozenset({Scope.ingest_write}),
        "digest": "b" * 64,
        "created_at": AT,
    }
    return ApiKeyRecord(**{**fields, **overrides})


def test_the_insert_names_every_column_and_no_plaintext() -> None:
    text, params = compiled(api_key_insert(sample_record(), owner_id=9))
    assert "INSERT INTO api_keys" in text
    for column in ("owner_id", "name", "key_hash", "scopes", "last_used_at", "revoked_at"):
        assert column in text
    assert "secret" not in text.lower()
    assert "b" * 64 in params.values()
    assert 9 in params.values()


def test_the_select_returns_revoked_keys_by_default() -> None:
    """Verification must find the row to know it was revoked, and the screen shows it."""
    text, _ = compiled(api_key_select())
    assert "revoked_at IS NULL" not in text
    text, _ = compiled(api_key_select(include_revoked=False))
    assert "api_keys.revoked_at IS NULL" in text


def test_the_select_filters_by_owner_and_orders_stably() -> None:
    text, params = compiled(api_key_select(owner_id=9))
    assert "api_keys.owner_id = %(owner_id_1)s" in text
    assert params["owner_id_1"] == 9
    assert text.strip().endswith("ORDER BY api_keys.id")


def test_the_revoke_update_cannot_move_an_existing_timestamp() -> None:
    """The ``revoked_at IS NULL`` guard is what makes a second revoke a no-op."""
    text, params = compiled(api_key_revoke(3, at=LATER))
    assert text.startswith("UPDATE api_keys SET revoked_at=%(revoked_at)s")
    assert params["revoked_at"] == LATER
    assert "api_keys.revoked_at IS NULL" in text


def test_the_touch_update_carries_the_interval_as_a_bound() -> None:
    """The interval test is in the WHERE clause: no read-modify-write race."""
    text, params = compiled(api_key_touch(3, at=LATER, interval_seconds=60))
    assert "api_keys.last_used_at IS NULL" in text
    assert "api_keys.last_used_at < %(last_used_at_1)s" in text
    assert params["last_used_at_1"] == LATER - timedelta(seconds=60)
    assert params["last_used_at"] == LATER


def test_a_negative_touch_interval_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        api_key_touch(3, at=AT, interval_seconds=-1)


def test_the_touch_interval_default_is_a_constant_not_a_magic_number() -> None:
    assert DEFAULT_TOUCH_INTERVAL_SECONDS > 0


# --- store identity ----------------------------------------------------------


def test_ids_come_from_the_store_and_are_sequential(
    digest: KeyDigest, store: InMemoryApiKeyStore
) -> None:
    first = issue_key(
        store, digest, name="a", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    second = issue_key(
        store, digest, name="b", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    assert (first.record.id, second.record.id) == (1, 2)
    assert [record.name for record in store.list()] == ["a", "b"]


def test_a_refused_issue_does_not_consume_an_id(
    store: InMemoryApiKeyStore, digest: KeyDigest
) -> None:
    with pytest.raises(ValueError, match="named"):
        issue_key(
            store,
            digest,
            name="  ",
            owner="o@corp",
            scopes=frozenset({Scope.ingest_write}),
            at=AT,
        )
    good = issue_key(
        store, digest, name="a", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    assert good.record.id == 1


def test_a_store_that_returns_the_wrong_id_is_refused(store: InMemoryApiKeyStore) -> None:
    """The store owns identity; a builder that returns a different id is a bug.

    Silently storing it would make the digest cover an id the row does not have,
    so the key would be issued and then never verify.
    """

    def build(key_id: int) -> ApiKeyRecord:
        return sample_record(id=key_id + 1)

    with pytest.raises(ValueError, match=r"build\(\) returned id"):
        store.create(build)
    assert len(store) == 0


def test_the_store_reports_how_many_keys_it_holds(
    store: InMemoryApiKeyStore, digest: KeyDigest
) -> None:
    assert len(store) == 0
    issue_key(
        store, digest, name="a", owner="o@corp", scopes=frozenset({Scope.ingest_write}), at=AT
    )
    assert len(store) == 1


def test_a_record_defaults_to_live_and_never_used() -> None:
    record = sample_record()
    assert record.active is True
    assert record.revoked_at is None
    assert record.last_used_at is None
    assert record.grants(Scope.ingest_write) is True
    assert record.grants(Scope.alerts_read) is False


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": 0}, "positive"),
        ({"name": "   "}, "named"),
        ({"owner": "  "}, "owner"),
        ({"digest": "short"}, "64 lowercase hex"),
        ({"digest": "A" * 64}, "64 lowercase hex"),
        ({"created_at": datetime(2026, 10, 5, 12, 0)}, "timezone-aware"),
        ({"revoked_at": datetime(2026, 10, 5, 12, 0)}, "timezone-aware"),
        ({"revoked_at": AT - timedelta(seconds=1)}, "cannot precede"),
    ],
)
def test_a_record_that_could_not_be_trusted_is_refused(
    overrides: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        sample_record(**overrides)


# --- authorisation: what a key may reach ------------------------------------


def test_scope_capabilities_are_a_subset_of_every_role_allowed_on_that_route() -> None:
    """The bound that makes a scope safe.

    For each (method, path) a key may call, the capabilities its scope grants must
    be held by *every* role the matrix permits there. So a key can never outrank
    the least-privileged human allowed on the route -- which is what stops an
    alerts:read key from inheriting anything an admin could do there.
    """
    for (method, path), scope in API_KEY_ROUTES.items():
        assert path in ROUTE_MATRIX, f"{method} {path} is not in the role matrix"
        allowed = ROUTE_MATRIX[path]
        shared = set.intersection(*(set(ROLE_CAPABILITIES[role]) for role in allowed))
        assert SCOPE_CAPABILITIES[scope] <= shared, f"{scope} exceeds {method} {path}"


def test_the_key_reachable_routes_are_mutating_or_reading_alerts() -> None:
    """FR-44 is machine-to-machine ingestion; the map is small on purpose."""
    assert set(API_KEY_ROUTES) == {
        ("POST", "/api/v1/ingest/flows"),
        ("POST", "/api/v1/ingest/logs"),
        ("GET", "/api/v1/alerts"),
    }


def test_the_key_management_routes_are_admin_only() -> None:
    for path in ("/api/v1/keys", "/api/v1/keys/{key_id}", "/api/v1/keys/scopes"):
        assert ROUTE_MATRIX[path] == frozenset({Role.ADMIN})


def test_only_admin_holds_the_api_keys_capability() -> None:
    holders = {role for role, caps in ROLE_CAPABILITIES.items() if Capability.API_KEYS in caps}
    assert holders == {Role.ADMIN}


def test_a_key_principal_grants_exactly_its_scopes() -> None:
    """A key has no role, and its capabilities are the scopes' union -- nothing else."""
    from app.auth.rbac import Principal

    read_key = Principal(
        role=None,
        subject="api-key:1",
        kind=PrincipalKind.api_key,
        scopes=frozenset({Scope.alerts_read}),
        key_id=1,
    )
    assert capabilities_of_principal(read_key) == frozenset({Capability.READ})
    assert Capability.INGEST not in capabilities_of_principal(read_key)

    ingest_key = Principal(
        role=None,
        subject="api-key:2",
        kind=PrincipalKind.api_key,
        scopes=frozenset({Scope.ingest_write, Scope.alerts_read}),
        key_id=2,
    )
    assert capabilities_of_principal(ingest_key) == frozenset({Capability.INGEST, Capability.READ})


def test_a_key_principal_with_no_scopes_grants_nothing() -> None:
    """An empty scope set on a key principal grants nothing at all.

    The record refuses to be built without a scope; the principal type does not,
    and must not read as "everything" if one is ever built another way.
    """
    from app.auth.rbac import Principal

    key = Principal(
        role=None,
        subject="api-key:9",
        kind=PrincipalKind.api_key,
        scopes=frozenset(),
        key_id=9,
    )
    assert capabilities_of_principal(key) == frozenset()


def test_a_user_principal_without_a_role_fails_loudly() -> None:
    from app.auth.rbac import Principal

    with pytest.raises(ValueError, match="must carry a role"):
        capabilities_of_principal(Principal(role=None, subject="alice"))


# --- through the API ---------------------------------------------------------


def test_an_admin_issues_a_key_and_is_shown_the_secret_once(client: TestClient) -> None:
    body = issued(client)
    assert body["secret"].startswith(f"{API_KEY_PREFIX}{body['id']}_")
    assert body["prefix"] == f"{API_KEY_PREFIX}{body['id']}_"
    assert body["scopes"] == ["ingest:write"]
    assert body["revoked_at"] is None
    assert body["last_used_at"] is None


def test_the_listing_never_carries_the_secret(client: TestClient) -> None:
    """Exposed exactly once means every later read must not have it."""
    body = issued(client)
    listing = client.get("/api/v1/keys", headers=headers(client.app.state.token_service))  # type: ignore[attr-defined]
    assert listing.status_code == 200
    assert "secret" not in listing.text
    assert body["secret"] not in listing.text
    item = listing.json()["items"][0]
    assert item["prefix"] == body["prefix"]
    assert item["id"] == body["id"]


def test_issuing_twice_shows_two_different_secrets(client: TestClient) -> None:
    first = issued(client, name="a")
    second = issued(client, name="b")
    assert first["secret"] != second["secret"]
    assert first["id"] != second["id"]


def test_the_secret_is_nowhere_but_the_one_response(client: TestClient) -> None:
    """The strongest form of "exactly once": a scan of everything else that exists."""
    body = issued(client)
    store: InMemoryApiKeyStore = client.app.state.api_key_store  # type: ignore[attr-defined]
    secret_half = body["secret"].split("_", 3)[3]
    for record in store.list():
        assert body["secret"] not in repr(record)
        assert secret_half not in record.digest
    for entry in all_entries(client):
        assert body["secret"] not in repr(entry.record)
        assert body["secret"] not in repr(entry.record.detail)


def test_the_creation_of_a_key_is_audited_without_its_material(client: TestClient) -> None:
    body = issued(client)
    actions = [entry.record.action for entry in all_entries(client)]
    assert AuditAction.key_create in actions
    entry = next(e for e in all_entries(client) if e.record.action is AuditAction.key_create)
    assert entry.record.target_type == "api_key"
    assert entry.record.target_id == str(body["id"])
    assert entry.record.detail["name"] == body["name"]
    assert entry.record.detail["scopes"] == ["ingest:write"]
    assert entry.record.actor == "admin@corp"


def test_an_unknown_scope_is_refused_with_the_allowed_set(client: TestClient) -> None:
    response = client.post(
        "/api/v1/keys",
        json={"name": "c", "scopes": ["ingest:read"]},
        headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
    )
    assert response.status_code == 400
    assert "alerts:read" in response.json()["detail"]
    assert "ingest:write" in response.json()["detail"]
    assert list(client.app.state.api_key_store.list()) == []  # type: ignore[attr-defined]


def test_an_empty_scope_list_is_refused_at_the_edge(client: TestClient) -> None:
    response = client.post(
        "/api/v1/keys",
        json={"name": "c", "scopes": []},
        headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
    )
    assert response.status_code == 422


def test_an_empty_scope_list_is_refused_by_the_endpoint_too(client: TestClient) -> None:
    """The guard behind pydantic's ``min_length``, for a caller that skips it.

    A key that can do nothing is a misconfiguration, and the alternative reading of
    an empty set -- "everything" -- is the vulnerability D-043 exists to prevent.
    """
    from app.api.v1.endpoints.api_keys import create_key
    from app.auth.rbac import Principal
    from app.schemas.api_key import ApiKeyCreate
    from fastapi import Request
    from starlette.responses import Response

    request = Request(scope={"type": "http", "app": client.app, "path": "/api/v1/keys"})
    caller = Principal(role=Role.ADMIN, subject="admin@corp")
    with pytest.raises(HTTPException) as caught:
        create_key(ApiKeyCreate.model_construct(name="c", scopes=[]), request, Response(), caller)
    assert caught.value.status_code == 400
    assert "at least one scope" in caught.value.detail


def test_a_nameless_key_is_refused(client: TestClient) -> None:
    for name in ("", "   ", "x" * 121):
        response = client.post(
            "/api/v1/keys",
            json={"name": name, "scopes": ["ingest:write"]},
            headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
        )
        assert response.status_code in (400, 422), name


@pytest.mark.parametrize(
    "method,path",
    [("get", "/api/v1/keys"), ("post", "/api/v1/keys"), ("get", "/api/v1/keys/scopes")],
)
def test_key_management_is_refused_to_every_other_role(
    client: TestClient, method: str, path: str
) -> None:
    for role in ("viewer", "analyst", "responder"):
        kwargs: dict[str, Any] = {}
        if method == "post":
            kwargs["json"] = {"name": "c", "scopes": ["ingest:write"]}
        response = getattr(client, method)(
            path,
            headers=headers(client.app.state.token_service, role),  # type: ignore[attr-defined]
            **kwargs,
        )
        assert response.status_code == 403, role


def test_key_management_requires_a_credential(client: TestClient) -> None:
    assert client.get("/api/v1/keys").status_code == 401
    created = client.post("/api/v1/keys", json={"name": "c", "scopes": ["ingest:write"]})
    assert created.status_code == 401


def test_the_scopes_route_lists_what_the_authorisation_table_understands(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/keys/scopes", headers=headers(client.app.state.token_service))  # type: ignore[attr-defined]
    assert response.status_code == 200
    items = {item["name"]: item["capabilities"] for item in response.json()["items"]}
    assert items == {
        "ingest:write": ["ingest"],
        "alerts:read": ["read"],
    }


def test_a_key_with_the_ingest_scope_can_ingest(client: TestClient) -> None:
    body = issued(client)
    response = client.post("/api/v1/ingest/flows", json=[FLOW], headers=key_headers(body["secret"]))
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] == 1


def test_a_key_can_be_presented_as_a_bearer_token_too(client: TestClient) -> None:
    """Collectors do both; the shape decides which credential path is taken."""
    body = issued(client)
    response = client.post(
        "/api/v1/ingest/flows",
        json=[FLOW],
        headers={"Authorization": f"Bearer {body['secret']}"},
    )
    assert response.status_code == 200


def test_a_key_that_lost_an_owner_still_has_a_subject(client: TestClient) -> None:
    """The credential is what acted: renaming the owner must not rewrite history."""
    body = issued(client)
    store: InMemoryApiKeyStore = client.app.state.api_key_store  # type: ignore[attr-defined]
    record = store.get(body["id"])
    assert record is not None
    assert f"api-key:{record.id}" != record.owner


def test_ingesting_with_a_key_is_audited_as_the_key(client: TestClient) -> None:
    body = issued(client)
    client.post("/api/v1/ingest/flows", json=[FLOW], headers=key_headers(body["secret"]))
    ingest_entries = [
        entry for entry in all_entries(client) if entry.record.action is AuditAction.ingest_flows
    ]
    assert ingest_entries
    assert ingest_entries[0].record.actor == f"api-key:{body['id']}"


def test_a_key_without_the_ingest_scope_cannot_ingest(client: TestClient) -> None:
    body = issued(client, scopes=["alerts:read"], name="reader")
    response = client.post("/api/v1/ingest/flows", json=[FLOW], headers=key_headers(body["secret"]))
    assert response.status_code == 403


def test_a_key_with_the_alerts_scope_can_read_alerts(client: TestClient) -> None:
    body = issued(client, scopes=["alerts:read"], name="reader")
    response = client.get("/api/v1/alerts", headers=key_headers(body["secret"]), params=window())
    assert response.status_code == 200, response.text


def test_a_key_cannot_reach_a_route_it_was_not_granted(client: TestClient) -> None:
    """Default-deny, in both directions.

    A route absent from API_KEY_ROUTES does not take keys at all, even one whose
    role matrix would have allowed the owner.
    """
    body = issued(client, scopes=["ingest:write", "alerts:read"], name="wide")
    for method, path, payload in (
        ("get", "/api/v1/webhooks", None),
        ("post", "/api/v1/webhooks", {"url": "https://hooks.example.com/x"}),
        ("post", "/api/v1/alerts/17/verdict", {"verdict": "true_positive"}),
        ("get", "/api/v1/audit", None),
        ("post", "/api/v1/keys", {"name": "c", "scopes": ["ingest:write"]}),
    ):
        kwargs: dict[str, Any] = {"headers": key_headers(body["secret"]), "params": window()}
        if method == "post":
            kwargs["json"] = payload
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 403, f"{method} {path}: {response.text}"
        assert response.json()["detail"] == "this route does not accept API keys"


def test_a_key_route_still_refuses_a_key_with_insufficient_scope(
    client: TestClient,
) -> None:
    """The route accepts keys; this key does not hold the scope the route needs."""
    body = issued(client, scopes=["alerts:read"], name="reader")
    response = client.post("/api/v1/ingest/logs", json=[], headers=key_headers(body["secret"]))
    assert response.status_code == 403
    assert "lacks a scope granting" in response.json()["detail"]
    assert "does not accept API keys" not in response.json()["detail"]


def test_a_revoked_key_is_rejected_by_the_very_next_request(client: TestClient) -> None:
    """The acceptance criterion, through HTTP, with no cache in between."""
    body = issued(client)
    first = client.post("/api/v1/ingest/flows", json=[FLOW], headers=key_headers(body["secret"]))
    assert first.status_code == 200
    revoked = client.delete(
        f"/api/v1/keys/{body['id']}",
        headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    after = client.post("/api/v1/ingest/flows", json=[FLOW], headers=key_headers(body["secret"]))
    assert after.status_code == 401
    assert after.json()["detail"] == "authentication required"


def test_revoking_an_unknown_key_is_a_404(client: TestClient) -> None:
    response = client.delete(
        "/api/v1/keys/404",
        headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
    )
    assert response.status_code == 404


def test_revoking_twice_is_idempotent_and_audited_once(client: TestClient) -> None:
    body = issued(client)
    admin = headers(client.app.state.token_service)  # type: ignore[attr-defined]
    first = client.delete(f"/api/v1/keys/{body['id']}", headers=admin).json()
    second = client.delete(f"/api/v1/keys/{body['id']}", headers=admin)
    assert second.status_code == 200
    assert second.json()["revoked_at"] == first["revoked_at"]
    revokes = [
        entry for entry in all_entries(client) if entry.record.action is AuditAction.key_revoke
    ]
    assert len(revokes) == 1


def test_a_revoked_key_still_appears_in_the_listing(client: TestClient) -> None:
    """The listing is the record of what existed, not the set of what works."""
    body = issued(client)
    admin = headers(client.app.state.token_service)  # type: ignore[attr-defined]
    client.delete(f"/api/v1/keys/{body['id']}", headers=admin)
    listing = client.get("/api/v1/keys", headers=admin).json()
    assert [item["id"] for item in listing["items"]] == [body["id"]]
    assert listing["items"][0]["revoked_at"] is not None


def test_a_revoked_key_cannot_be_resurrected_by_the_same_secret(client: TestClient) -> None:
    """Issuing again mints a new secret and a new row; the old string stays dead."""
    body = issued(client)
    admin = headers(client.app.state.token_service)  # type: ignore[attr-defined]
    client.delete(f"/api/v1/keys/{body['id']}", headers=admin)
    replacement = issued(client, name="collector-2")
    assert replacement["secret"] != body["secret"]
    store: InMemoryApiKeyStore = client.app.state.api_key_store  # type: ignore[attr-defined]
    assert [record.active for record in store.list()] == [False, True]


def test_a_used_key_reports_when_it_was_last_used(client: TestClient) -> None:
    body = issued(client)
    assert body["last_used_at"] is None
    client.post("/api/v1/ingest/flows", json=[FLOW], headers=key_headers(body["secret"]))
    listing = client.get(
        "/api/v1/keys", headers=headers(client.app.state.token_service)  # type: ignore[attr-defined]
    ).json()
    assert listing["items"][0]["last_used_at"] is not None


def test_two_credentials_at_once_are_refused(client: TestClient) -> None:
    """An authority ambiguity: the failure mode of guessing is the wrong credential.

    Both credentials here would individually authorise the request -- an admin
    token and an ingest-scoped key -- which is exactly when precedence would be a
    silent decision. The request is refused instead.
    """
    key = issued(client)
    user = headers(client.app.state.token_service)  # type: ignore[attr-defined]
    response = client.post(
        "/api/v1/ingest/flows",
        json=[FLOW],
        headers={**user, "X-API-Key": key["secret"]},
    )
    assert response.status_code == 401

    second = issued(client, name="second")
    response = client.post(
        "/api/v1/ingest/flows",
        json=[FLOW],
        headers={"Authorization": f"Bearer {key['secret']}", "X-API-Key": second["secret"]},
    )
    assert response.status_code == 401


def test_a_header_that_is_not_a_key_is_not_treated_as_one(client: TestClient) -> None:
    """X-API-Key carries a JWT by mistake: a 401, not a fallback to the header."""
    # JWT-shaped on purpose; there is no credential in it. The pragma below is the
    # repository's convention for a scanner false positive (see .secrets.baseline).
    jwt_shaped = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9.x"  # pragma: allowlist secret
    response = client.post(
        "/api/v1/ingest/flows",
        json=[FLOW],
        headers={"X-API-Key": jwt_shaped},
    )
    assert response.status_code == 401


def test_a_user_token_still_works_everywhere(client: TestClient) -> None:
    """The key path is additive: R-53's role matrix is not bypassed, it is extended."""
    service = client.app.state.token_service  # type: ignore[attr-defined]
    assert (
        client.post(
            "/api/v1/ingest/flows", json=[FLOW], headers=headers(service, "analyst")
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/keys",
            json={"name": "c", "scopes": ["ingest:write"]},
            headers=headers(service, "admin"),
        ).status_code
        == 201
    )
    assert (
        client.get(
            "/api/v1/alerts", headers=headers(service, "viewer"), params=window()
        ).status_code
        == 200
    )


def test_a_key_without_a_store_fails_loudly(settings: Settings, auth: TokenService) -> None:
    """No silent fallback: a missing store must not be read as "no keys issued"."""
    import app.main as main_module

    built = create_app(settings)
    built.state.token_service = auth
    del built.state.api_key_store
    with TestClient(built) as test_client, pytest.raises(RuntimeError, match="api_key_store"):
        test_client.post(
            "/api/v1/ingest/flows",
            json=[FLOW],
            headers={"X-API-Key": f"{API_KEY_PREFIX}1_" + "a" * 43},
        )
    assert main_module is not None


def test_a_key_without_a_digest_fails_loudly(settings: Settings, auth: TokenService) -> None:
    built = create_app(settings)
    built.state.token_service = auth
    del built.state.api_key_digest
    with TestClient(built) as test_client, pytest.raises(RuntimeError, match="api_key_digest"):
        test_client.post(
            "/api/v1/ingest/flows",
            json=[FLOW],
            headers={"X-API-Key": f"{API_KEY_PREFIX}1_" + "a" * 43},
        )


def test_the_store_and_digest_are_installed_by_the_composition_root(client: TestClient) -> None:
    assert isinstance(client.app.state.api_key_store, InMemoryApiKeyStore)  # type: ignore[attr-defined]
    assert isinstance(client.app.state.api_key_digest, KeyDigest)  # type: ignore[attr-defined]


def to_walk(routes: Any) -> list[Any]:
    """Every route object, walking the ``_IncludedRouter`` containers FastAPI mounts."""
    found: list[Any] = []
    for route in routes:
        found.append(route)
        for attribute in ("original_router", "router"):
            nested = getattr(route, attribute, None)
            if nested is not None:
                found.extend(to_walk(getattr(nested, "routes", [])))
    return found


def test_every_key_reachable_route_exists_on_the_built_app(client: TestClient) -> None:
    """An entry with no live route would grant a path that does not exist.

    Checked against the built app rather than the router module, so a route
    removed from the application fails here. ``include_router`` nests the routes
    inside a container, so the walk recurses; reading ``app.routes`` directly
    would see only the documentation endpoints and pass vacuously.
    """
    live: set[tuple[str, str]] = set()
    for route in to_walk(client.app.routes):  # type: ignore[attr-defined]
        path = getattr(route, "path", None)
        if not isinstance(path, str):
            continue
        for method in getattr(route, "methods", ()) or ():
            live.add((method, path))
    assert set(API_KEY_ROUTES) <= live
