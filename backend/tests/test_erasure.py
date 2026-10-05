"""T-314: GDPR erasure -- cascades, logs, and is idempotent (NFR-05, R-37).

Three claims, and each is asserted where it could be false:

* **Cascades across stores.** Two stores change in one call, including the
  cascade the schema itself declares (``api_keys.owner_id`` carries
  ``ON DELETE CASCADE``), and a target of the wrong kind reports ``0`` rather than
  being skipped in silence. A second test asserts that the stores this service
  deliberately does *not* rewrite are named in every report -- a report that lists
  only what changed reads as "nothing else holds this subject".
* **Logs the action.** The ledger is append-only and holds tombstones, not
  identifiers; the audit entry is the endpoint's job and is tested through HTTP.
* **Idempotent.** A second request for the same subject touches no target,
  appends no ledger entry and answers ``already_erased`` -- so the property does
  not depend on the targets happening to be idempotent.

The identifier must never appear in the report, the ledger or a tombstone: each
of those is asserted directly, because "we erased them" is a claim about where the
data is not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.auth.api_keys import InMemoryApiKeyStore, KeyDigest, Scope, issue_key
from app.services.erasure import (
    DEFAULT_LEDGER_LIMIT,
    MAX_LEDGER_LIMIT,
    EntityRedactionTarget,
    ErasureKind,
    ErasureService,
    ErasureSubject,
    InMemoryEntityStore,
    InMemoryErasureLedger,
    InMemoryUserStore,
    LedgerEntry,
    Redactor,
    UserDeletionTarget,
)

APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
AT = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
SUBJECT_EMAIL = "bob@corp.example"  # pragma: allowlist secret
HOSTNAME = "web-07.internal.example"


def redactor(secret: str = APP_SECRET) -> Redactor:
    return Redactor(secret)


def subject(kind: ErasureKind = ErasureKind.user, value: str = SUBJECT_EMAIL) -> ErasureSubject:
    return ErasureSubject(kind=kind, value=value)


def service(
    *,
    entities: InMemoryEntityStore | None = None,
    users: InMemoryUserStore | None = None,
    ledger: InMemoryErasureLedger | None = None,
    redact: Redactor | None = None,
) -> ErasureService:
    """A service over whichever targets a test cares about, entity first."""
    targets = []
    if entities is not None:
        targets.append(EntityRedactionTarget(entities))
    if users is not None:
        targets.append(UserDeletionTarget(users))
    # `or` would be wrong here: an empty ledger is falsy (it defines __len__), so
    # a caller passing one to watch it grow would get a different ledger back.
    return ErasureService(
        targets,
        ledger=ledger if ledger is not None else InMemoryErasureLedger(),
        redactor=redact if redact is not None else redactor(),
    )


# --- the subject -------------------------------------------------------------


def test_a_subject_must_name_a_value() -> None:
    for value in ("", "   "):
        with pytest.raises(ValueError, match="must name a value"):
            ErasureSubject(kind=ErasureKind.user, value=value)


def test_an_implausibly_long_subject_is_refused() -> None:
    with pytest.raises(ValueError, match="over the 512 limit"):
        ErasureSubject(kind=ErasureKind.entity, value="x" * 513)


def test_the_kind_is_required_and_closed() -> None:
    assert {kind.value for kind in ErasureKind} == {"user", "entity"}
    with pytest.raises(ValueError):
        ErasureSubject(kind="person", value=SUBJECT_EMAIL)  # type: ignore[arg-type]


# --- the tombstone -----------------------------------------------------------


def test_a_tombstone_is_a_prefixed_pseudonym_not_the_identifier() -> None:
    tombstone = redactor().tombstone(subject())
    assert tombstone.startswith("erased:")
    assert SUBJECT_EMAIL not in tombstone
    assert len(tombstone) == len("erased:") + 32


def test_the_same_subject_gives_the_same_tombstone() -> None:
    """Stable within a deployment: a second request is recognisably the same person."""
    assert redactor().tombstone(subject()) == redactor().tombstone(subject())


def test_the_kind_is_part_of_the_tombstone() -> None:
    """A user named like a host is a different subject from that host."""
    same_value = "bob"
    assert redactor().tombstone(
        ErasureSubject(kind=ErasureKind.user, value=same_value)
    ) != redactor().tombstone(ErasureSubject(kind=ErasureKind.entity, value=same_value))


def test_two_deployments_do_not_share_tombstones() -> None:
    """The key comes from AEGIS_SECRET_KEY.

    A dump from one deployment cannot be matched against another environment's
    tombstones.
    """
    assert redactor().tombstone(subject()) != redactor("y" * 40).tombstone(subject())


def test_a_short_application_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        Redactor("too-short")


def test_a_tombstone_can_be_matched_against_its_subject() -> None:
    """What a repeat request does: derive and compare, without storing the value."""
    tombstone = redactor().tombstone(subject())
    assert redactor().matches(subject(), tombstone) is True
    assert redactor().matches(subject(value="someone-else"), tombstone) is False


def test_a_tombstone_records_itself_as_a_pseudonym() -> None:
    """The ledger entry refuses anything that is not an ``erased:`` pseudonym."""
    with pytest.raises(ValueError, match="pseudonym"):
        LedgerEntry(
            sequence=1,
            tombstone=SUBJECT_EMAIL,
            kind=ErasureKind.user,
            at=AT,
            requested_by="admin@corp",
            targets=(),
        )


# --- the ledger --------------------------------------------------------------


def test_the_ledger_records_and_reports_a_tombstone() -> None:
    ledger = InMemoryErasureLedger()
    tombstone = redactor().tombstone(subject())
    assert ledger.has(tombstone) is False
    ledger.append(
        LedgerEntry(
            sequence=1,
            tombstone=tombstone,
            kind=ErasureKind.user,
            at=AT,
            requested_by="admin@corp",
            targets=(("users", 1),),
        )
    )
    assert ledger.has(tombstone) is True
    assert len(ledger) == 1
    assert ledger.next_sequence() == 2
    assert ledger.entries(limit=10)[0].targets == (("users", 1),)


def test_the_ledger_lists_newest_first_and_pages_on_a_cursor() -> None:
    ledger = InMemoryErasureLedger()
    for index in range(1, 4):
        ledger.append(
            LedgerEntry(
                sequence=index,
                tombstone=f"erased:{index:032d}",
                kind=ErasureKind.entity,
                at=AT + timedelta(minutes=index),
                requested_by="admin@corp",
                targets=(),
            )
        )
    assert [entry.sequence for entry in ledger.entries(limit=10)] == [3, 2, 1]
    assert [entry.sequence for entry in ledger.entries(limit=10, before=3)] == [2, 1]


def test_the_ledger_refuses_a_limit_below_one() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        InMemoryErasureLedger().entries(limit=0)


def test_a_ledger_entry_must_be_attributable_and_aware() -> None:
    fields = {
        "sequence": 1,
        "tombstone": "erased:" + "a" * 32,
        "kind": ErasureKind.user,
        "at": AT,
        "requested_by": "admin@corp",
        "targets": (),
    }
    with pytest.raises(ValueError, match="1-based"):
        LedgerEntry(**{**fields, "sequence": 0})
    with pytest.raises(ValueError, match="timezone-aware"):
        LedgerEntry(**{**fields, "at": datetime(2026, 10, 5, 12, 0)})
    with pytest.raises(ValueError, match="who requested"):
        LedgerEntry(**{**fields, "requested_by": "  "})


def test_the_ledger_has_no_way_to_remove_an_entry() -> None:
    """A ledgers whose entries could be removed could claim an erasure never made."""
    names = {name for name in dir(InMemoryErasureLedger) if not name.startswith("_")}
    assert not {name for name in names if name.lower() in {"delete", "remove", "purge", "clear"}}


# --- the service: the cascade -------------------------------------------------


def test_a_service_with_no_targets_is_refused() -> None:
    """It would report success while erasing nothing."""
    with pytest.raises(ValueError, match="no targets"):
        ErasureService([], ledger=InMemoryErasureLedger(), redactor=redactor())


def test_duplicate_target_names_are_refused() -> None:
    """Two stores under one name would make the report unreadable."""
    entities = InMemoryEntityStore()
    with pytest.raises(ValueError, match="unique"):
        ErasureService(
            [EntityRedactionTarget(entities), EntityRedactionTarget(entities)],
            ledger=InMemoryErasureLedger(),
            redactor=redactor(),
        )


def test_erasing_an_entity_redacts_it_and_reports_the_count() -> None:
    entities = InMemoryEntityStore()
    entities.add("host", HOSTNAME)
    entities.add("host", "other.internal.example")
    report = service(entities=entities).erase(
        subject(ErasureKind.entity, HOSTNAME), requested_by="admin@corp", at=AT
    )
    assert report.kind is ErasureKind.entity
    assert report.affected == 1
    assert report.changed_anything is True
    assert report.already_erased is False
    assert report.ledger_sequence == 1
    assert HOSTNAME not in entities.values()
    assert report.tombstone in entities.values()


def test_erasing_a_user_cascades_to_the_keys_the_schema_cascades_to() -> None:
    """``api_keys.owner_id`` is ``ON DELETE CASCADE``, so the keys go too."""
    keys = InMemoryApiKeyStore()
    digest = KeyDigest(APP_SECRET)
    for name in ("collector-a", "collector-b"):
        issue_key(
            keys,
            digest,
            name=name,
            owner=SUBJECT_EMAIL,
            scopes=frozenset({Scope.ingest_write}),
            at=AT,
        )
    issue_key(
        keys,
        digest,
        name="other",
        owner="carol@corp.example",
        scopes=frozenset({Scope.ingest_write}),
        at=AT,
    )

    users = InMemoryUserStore(keys=keys)
    users.add(SUBJECT_EMAIL)
    users.add("carol@corp.example")

    report = service(users=users).erase(subject(), requested_by="admin@corp", at=AT)
    assert report.affected == 1  # the user row
    assert storage_names(keys) == ["other"]  # their two keys went with it
    assert len(users) == 1


def storage_names(store: InMemoryApiKeyStore) -> list[str]:
    """The names of the keys a store still holds, for cascade assertions."""
    return sorted(record.name for record in store.list())


def test_every_store_is_named_in_the_report_that_a_request_reaches() -> None:
    """Two requests, one cascade, and every registered store in both reports.

    An entity erasure is about what was observed; an account erasure is about the
    account. Each report names both stores -- the second with a zero for the store
    it did not need -- so a report can never be read as a complete inventory of
    where a subject's data lives.
    """
    entities = InMemoryEntityStore()
    entities.add("host", HOSTNAME)
    entities.add("user", SUBJECT_EMAIL)
    users = InMemoryUserStore()
    users.add(SUBJECT_EMAIL)
    cascade = service(entities=entities, users=users)

    observed = cascade.erase(
        subject(ErasureKind.entity, HOSTNAME), requested_by="admin@corp", at=AT
    )
    assert [outcome.name for outcome in observed.outcomes] == ["entities", "users"]
    assert [outcome.affected for outcome in observed.outcomes] == [1, 0]

    account = cascade.erase(subject(), requested_by="admin@corp", at=AT)
    assert [outcome.affected for outcome in account.outcomes] == [0, 1]
    assert account.affected == 1
    assert len(users) == 0


def test_a_target_of_another_kind_reports_zero_and_is_not_touched() -> None:
    """Skipping is not a failure, and the report still names the store."""
    entities = InMemoryEntityStore()
    entities.add("host", HOSTNAME)
    report = service(entities=entities).erase(subject(), requested_by="admin@corp", at=AT)
    assert [outcome.name for outcome in report.outcomes] == ["entities"]
    assert report.affected == 0
    assert len(entities) == 1


def test_a_subject_with_no_data_anywhere_is_a_successful_erasure_of_nothing() -> None:
    report = service(entities=InMemoryEntityStore(), users=InMemoryUserStore()).erase(
        subject(), requested_by="admin@corp", at=AT
    )
    assert report.affected == 0
    assert report.changed_anything is False
    assert report.already_erased is False
    assert report.ledger_sequence == 1


# --- the service: preserved stores and the report -----------------------------


def test_every_report_names_the_stores_it_did_not_rewrite() -> None:
    report = service(entities=InMemoryEntityStore()).erase(
        subject(ErasureKind.entity, HOSTNAME), requested_by="admin@corp", at=AT
    )
    names = {item.name for item in report.preserved}
    assert names == {"audit_log", "verdicts"}
    assert all(item.reason for item in report.preserved)


def test_the_report_never_carries_the_identifier() -> None:
    """A report is echoed into responses, logs and tickets: it must not be a copy."""
    entities = InMemoryEntityStore()
    entities.add("host", HOSTNAME)
    report = service(entities=entities).erase(
        subject(ErasureKind.entity, HOSTNAME), requested_by="admin@corp", at=AT
    )
    assert HOSTNAME not in repr(report)
    assert SUBJECT_EMAIL not in repr(report)


def test_the_ledger_never_carries_the_identifier() -> None:
    ledger = InMemoryErasureLedger()
    service(entities=InMemoryEntityStore(), ledger=ledger).erase(
        subject(ErasureKind.entity, HOSTNAME), requested_by="admin@corp", at=AT
    )
    assert HOSTNAME not in repr(ledger.entries(limit=10))


def test_an_erasure_must_name_who_requested_it() -> None:
    for bad in ("", "   "):
        with pytest.raises(ValueError, match="who requested"):
            service(entities=InMemoryEntityStore()).erase(subject(), requested_by=bad, at=AT)


def test_an_naive_timestamp_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        service(entities=InMemoryEntityStore()).erase(
            subject(), requested_by="admin@corp", at=datetime(2026, 10, 5, 12, 0)
        )


# --- the service: idempotence -------------------------------------------------


def test_a_second_erasure_touches_nothing_and_says_so() -> None:
    """Idempotent because of the ledger, not because the targets happen to be."""
    entities = InMemoryEntityStore()
    entities.add("host", HOSTNAME)
    ledger = InMemoryErasureLedger()
    cascade = service(entities=entities, ledger=ledger)
    first = cascade.erase(subject(ErasureKind.entity, HOSTNAME), requested_by="admin@corp", at=AT)
    second = cascade.erase(
        subject(ErasureKind.entity, HOSTNAME), requested_by="admin@corp", at=AT + timedelta(days=1)
    )
    assert first.already_erased is False
    assert second.already_erased is True
    assert second.affected == 0
    assert second.changed_anything is False
    assert second.ledger_sequence is None
    assert len(ledger) == 1
    assert second.tombstone == first.tombstone
    # A repeat report is still a report: it names the stores that keep data, so an
    # auditor reading only the second answer is not told the cascade touched
    # nothing anywhere.
    assert [item.name for item in second.preserved] == [item.name for item in first.preserved]
    assert [outcome.name for outcome in second.outcomes] == ["entities"]


def test_a_second_erasure_reports_every_target_with_zero() -> None:
    entities = InMemoryEntityStore()
    entities.add("host", HOSTNAME)
    cascade = service(entities=entities, users=InMemoryUserStore())
    cascade.erase(subject(ErasureKind.entity, HOSTNAME), requested_by="admin@corp", at=AT)
    second = cascade.erase(subject(ErasureKind.entity, HOSTNAME), requested_by="admin@corp", at=AT)
    assert [outcome.affected for outcome in second.outcomes] == [0, 0]


def test_a_user_subject_and_an_entity_subject_do_not_mark_each_other_done() -> None:
    """Two kinds, two stores, two tombstones -- and neither is a repeat of the other.

    An ``entity`` erasure is about what the platform observed (hosts, services and
    the users it saw in traffic); a ``user`` erasure is about an account. The same
    string in both is two requests, and the first must not answer for the second.
    """
    entities = InMemoryEntityStore()
    entities.add("host", "bob")
    users = InMemoryUserStore()
    users.add("bob")
    cascade = service(entities=entities, users=users)

    first = cascade.erase(subject(ErasureKind.entity, "bob"), requested_by="admin@corp", at=AT)
    assert first.affected == 1
    assert entities.values() == (first.tombstone,)

    second = cascade.erase(subject(ErasureKind.user, "bob"), requested_by="admin@corp", at=AT)
    assert second.already_erased is False
    assert second.affected == 1
    assert len(users) == 0
    assert second.tombstone != first.tombstone


# --- the ledger read path -----------------------------------------------------


def test_the_histogram_is_newest_first_and_bounded() -> None:
    cascade = service(entities=InMemoryEntityStore())
    for index in range(3):
        cascade.erase(
            subject(ErasureKind.entity, f"host-{index}.internal.example"),
            requested_by="admin@corp",
            at=AT + timedelta(minutes=index),
        )
    entries = cascade.histogram(limit=2)
    assert [entry.tombstone for entry in entries] == sorted(
        (entry.tombstone for entry in entries), reverse=True
    )
    assert len(entries) == 2
    assert cascade.histogram(limit=DEFAULT_LEDGER_LIMIT)[0].sequence == 3


def test_the_histogram_refuses_a_limit_outside_the_ceiling() -> None:
    """A caller asking for everything is asking for an unbounded scan."""
    cascade = service(entities=InMemoryEntityStore())
    with pytest.raises(ValueError, match="limit must be 1.."):
        cascade.histogram(limit=0)
    with pytest.raises(ValueError, match="limit must be 1.."):
        cascade.histogram(limit=MAX_LEDGER_LIMIT + 1)


def test_the_registered_targets_are_visible_in_cascade_order() -> None:
    cascade = service(entities=InMemoryEntityStore(), users=InMemoryUserStore())
    assert cascade.targets == ("entities", "users")


# --- the in-memory stores the targets sit on ---------------------------------


def test_the_entity_store_can_redact_across_kinds_or_within_one() -> None:
    """No kind given is the deployment-wide sweep; a kind given is one subject."""
    entities = InMemoryEntityStore()
    entities.add("host", "bob")
    entities.add("user", "bob")
    assert entities.redact_value("bob", replacement="erased:x", kind="host") == 1
    assert entities.values() == ("bob", "erased:x")
    assert entities.redact_value("bob", replacement="erased:y") == 1
    assert entities.values() == ("erased:x", "erased:y")


def test_two_kinds_with_one_value_stay_two_rows_after_redaction() -> None:
    """The schema's identity for an entity is (kind, value), so they do not collide."""
    entities = InMemoryEntityStore()
    entities.add("host", "bob")
    entities.add("user", "bob")
    assert entities.redact_value("bob", replacement="erased:x") == 2
    assert len(entities) == 2
    assert entities.values() == ("erased:x", "erased:x")


def test_the_entity_store_refuses_a_blank_value() -> None:
    with pytest.raises(ValueError, match="needs a value"):
        InMemoryEntityStore().add("host", "  ")


def test_the_user_store_erases_only_exact_identifiers() -> None:
    users = InMemoryUserStore()
    users.add("bob@corp.example")
    users.add("bobby@corp.example")
    assert users.erase_owner("bob@corp.example", replacement="") == 1
    assert len(users) == 1
    assert users.erase_owner("bob@corp.example", replacement="") == 0


def test_the_user_store_refuses_a_blank_identifier() -> None:
    with pytest.raises(ValueError, match="needs an identifier"):
        InMemoryUserStore().add(" ")


def test_erasing_a_user_marks_their_surviving_keys_revoked() -> None:
    """When a caller keeps the row and replaces the owner, the key must not live on."""
    keys = InMemoryApiKeyStore()
    digest = KeyDigest(APP_SECRET)
    issue_key(
        keys,
        digest,
        name="collector",
        owner=SUBJECT_EMAIL,
        scopes=frozenset({Scope.ingest_write}),
        at=AT,
    )
    assert keys.erase_owner(SUBJECT_EMAIL, replacement="erased:abc") == 1
    record = keys.list()[0]
    assert record.owner == "erased:abc"
    assert record.active is False


def test_a_target_asked_for_the_other_kind_does_nothing_even_directly() -> None:
    """The service filters by kind; the targets refuse too, so neither alone is the guard."""
    entities = InMemoryEntityStore()
    entities.add("host", HOSTNAME)
    users = InMemoryUserStore()
    users.add(SUBJECT_EMAIL)
    assert EntityRedactionTarget(entities).erase(subject(), replacement="erased:x") == 0
    assert entities.values() == (HOSTNAME,)
    assert (
        UserDeletionTarget(users).erase(subject(ErasureKind.entity, HOSTNAME), replacement="x") == 0
    )
    assert len(users) == 1


def test_an_untyped_kind_is_refused_naming_the_allowed_ones() -> None:
    """A request body or queue message can pass a string the annotation cannot stop."""
    with pytest.raises(ValueError, match="kind must be one of: user, entity"):
        ErasureSubject(kind=1, value=HOSTNAME)  # type: ignore[arg-type]


def test_a_ledger_without_next_sequence_still_numbers_its_entries() -> None:
    """``next_sequence`` is an optimisation, not part of the Protocol."""

    class Counted:
        """A ledger that only implements what the Protocol requires."""

        def __init__(self) -> None:
            self.entries_seen: list[LedgerEntry] = []

        def has(self, tombstone: str) -> bool:
            return any(entry.tombstone == tombstone for entry in self.entries_seen)

        def append(self, entry: LedgerEntry) -> None:
            self.entries_seen.append(entry)

        def entries(self, *, limit: int, before: int | None = None) -> tuple[LedgerEntry, ...]:
            del before
            return tuple(self.entries_seen[:limit])

    ledger = Counted()
    report = service(entities=InMemoryEntityStore(), ledger=ledger).erase(
        subject(ErasureKind.entity, HOSTNAME), requested_by="admin@corp", at=AT
    )
    assert report.ledger_sequence == 1
    assert report.already_erased is False
    assert ledger.entries_seen[0].tombstone == report.tombstone


def test_redacting_a_value_that_is_already_the_tombstone_keeps_one_row() -> None:
    """A second sweep over an already-erased value must not delete the row it kept."""
    entities = InMemoryEntityStore()
    entities.add("host", "erased:x")
    assert entities.redact_value("erased:x", replacement="erased:x") == 1
    assert entities.values() == ("erased:x",)
