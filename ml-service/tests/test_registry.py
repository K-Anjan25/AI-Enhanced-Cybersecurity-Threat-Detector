"""Tests for the model registry (R-68: immutable, no implicit latest)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aegis_ml.registry.model_registry import (
    ALLOWED_TRANSITIONS,
    FORBIDDEN_MODEL_IDS,
    ForbiddenModelId,
    ImmutableArtifact,
    InvalidTransition,
    ModelInfo,
    ModelNotLoaded,
    ModelRegistry,
    content_address,
    content_address_bytes,
)

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 6, 9, 30, tzinfo=UTC)


def flow(
    model_id: str,
    status: str = "active",
    loaded_at: datetime = T0,
    sha256: str = "a" * 64,
) -> ModelInfo:
    return ModelInfo(  # type: ignore[arg-type]
        model_id=model_id, kind="flow", status=status, sha256=sha256, loaded_at=loaded_at
    )


def test_get_unknown_model_raises_and_names_the_id() -> None:
    """A missing model must be reported precisely, not as a generic failure."""
    registry = ModelRegistry()

    with pytest.raises(ModelNotLoaded) as excinfo:
        registry.get("flownet@1.0.0")

    assert "flownet@1.0.0" in str(excinfo.value)
    assert "none" in str(excinfo.value)


def test_active_returns_none_when_nothing_is_loaded() -> None:
    registry = ModelRegistry()

    assert registry.active("flow") is None


def test_register_then_get_round_trips() -> None:
    registry = ModelRegistry()
    registry.register(flow("flownet@1.0.0"))

    assert registry.get("flownet@1.0.0").model_id == "flownet@1.0.0"
    assert registry.active("flow") is not None


def test_re_registering_an_id_with_different_content_is_refused() -> None:
    """R-68: no overwriting an artifact.

    A silent content change under a stable name is how a supply-chain
    substitution would hide, and it would also make a rollback to that id mean
    something different from what it meant yesterday.
    """
    registry = ModelRegistry()
    registry.register(flow("flownet@1.0.0"))

    with pytest.raises(ImmutableArtifact, match="cannot be re-registered"):
        registry.register(flow("flownet@1.0.0", sha256="b" * 64))


def test_re_registering_an_id_with_identical_content_is_a_no_op() -> None:
    """An unchanged redeploy is normal and must not fail."""
    registry = ModelRegistry()
    registry.register(flow("flownet@1.0.0"))

    registry.register(flow("flownet@1.0.0"))

    assert registry.get("flownet@1.0.0").sha256 == "a" * 64


def test_the_refusal_names_both_content_addresses() -> None:
    """The operator has to be able to see which two artifacts collided."""
    registry = ModelRegistry()
    registry.register(flow("flownet@1.0.0"))

    with pytest.raises(ImmutableArtifact) as raised:
        registry.register(flow("flownet@1.0.0", sha256="b" * 64))

    message = str(raised.value)
    assert "a" * 12 in message
    assert "b" * 12 in message


def test_two_active_models_of_one_kind_is_rejected() -> None:
    """Scores would be ambiguous if two flow models could both publish."""
    registry = ModelRegistry()
    registry.register(flow("flownet@1.0.0"))

    with pytest.raises(ValueError, match="already active"):
        registry.register(flow("flownet@1.1.0", loaded_at=T1))


def test_retiring_frees_the_kind_for_promotion() -> None:
    """Promotion is: retire the old version, then register the new one active."""
    registry = ModelRegistry()
    registry.register(flow("flownet@1.0.0"))
    registry.retire("flownet@1.0.0")

    assert registry.get("flownet@1.0.0").status == "retired"
    registry.register(flow("flownet@1.1.0", loaded_at=T1))
    assert registry.active("flow") is not None
    assert registry.active("flow").model_id == "flownet@1.1.0"  # type: ignore[union-attr]


def test_retire_unknown_model_raises() -> None:
    registry = ModelRegistry()

    with pytest.raises(ModelNotLoaded):
        registry.retire("nonexistent@0.0.1")


def test_kinds_are_tracked_independently() -> None:
    """An active flow model does not block an active log model."""
    registry = ModelRegistry()
    registry.register(flow("flownet@1.0.0"))
    registry.register(
        ModelInfo(
            model_id="lognet@1.0.0", kind="log", status="active", sha256="b" * 64, loaded_at=T1
        )
    )

    assert registry.active("flow").model_id == "flownet@1.0.0"  # type: ignore[union-attr]
    assert registry.active("log").model_id == "lognet@1.0.0"  # type: ignore[union-attr]


def test_snapshot_is_ordered_by_load_time() -> None:
    registry = ModelRegistry()
    registry.register(flow("second@1.0.0", status="staging", loaded_at=T1))
    registry.register(flow("first@1.0.0", status="staging", loaded_at=T0))

    assert [info.model_id for info in registry.snapshot()] == ["first@1.0.0", "second@1.0.0"]


def test_only_active_models_count_as_serving() -> None:
    registry = ModelRegistry()
    registry.register(flow("flownet@1.0.0", status="staging"))

    assert registry.get("flownet@1.0.0").is_serving is False


# --- T-212 acceptance: `latest` is not resolvable ---------------------------


class TestLatestIsNotResolvable:
    """R-68. A floating reference makes a score unattributable."""

    def test_get_refuses_latest(self) -> None:
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0"))

        with pytest.raises(ForbiddenModelId, match="not a resolvable model id"):
            registry.get("latest")

    def test_the_refusal_is_not_reported_as_a_missing_model(self) -> None:
        """Different remedy, so a different exception: typo vs forbidden pattern."""
        registry = ModelRegistry()

        with pytest.raises(ForbiddenModelId):
            registry.get("latest")
        with pytest.raises(ModelNotLoaded):
            registry.get("flownet@9.9.9")

    def test_every_forbidden_alias_is_refused(self) -> None:
        registry = ModelRegistry()

        for alias in sorted(FORBIDDEN_MODEL_IDS):
            with pytest.raises(ForbiddenModelId):
                registry.get(alias)

    def test_case_and_padding_do_not_sneak_one_through(self) -> None:
        registry = ModelRegistry()

        for variant in ("LATEST", "Latest", "  latest  "):
            with pytest.raises(ForbiddenModelId):
                registry.get(variant)

    def test_latest_cannot_be_registered(self) -> None:
        registry = ModelRegistry()

        with pytest.raises(ForbiddenModelId):
            registry.register(flow("latest"))

    def test_latest_cannot_be_promoted_or_retired(self) -> None:
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0", status="staging"))

        with pytest.raises(ForbiddenModelId):
            registry.promote("latest")
        with pytest.raises(ForbiddenModelId):
            registry.retire("latest")

    def test_a_model_info_cannot_even_be_built_with_it(self) -> None:
        """The id is rejected at construction, so it never enters the registry."""
        with pytest.raises(ForbiddenModelId):
            ModelInfo(
                model_id="latest",
                kind="flow",
                status="active",
                sha256="a" * 64,
                loaded_at=T0,
            )


# --- T-212 acceptance: promoting a retired version is refused ---------------


class TestRetiredIsTerminal:
    """The set of versions that have served traffic must stay append-only."""

    def test_promoting_a_retired_model_is_refused(self) -> None:
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0", status="active"))
        registry.register(flow("flownet@1.1.0", status="staging"))
        registry.promote("flownet@1.1.0")  # retires 1.0.0

        assert registry.get("flownet@1.0.0").status == "retired"
        with pytest.raises(InvalidTransition, match="cannot be promoted"):
            registry.promote("flownet@1.0.0")

    def test_the_refusal_says_what_to_do_instead(self) -> None:
        """A clear error names the remedy, not just the rule."""
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0"))
        registry.retire("flownet@1.0.0")

        with pytest.raises(InvalidTransition) as raised:
            registry.promote("flownet@1.0.0")

        message = str(raised.value)
        assert "terminal" in message
        assert "new model id" in message

    def test_retiring_twice_is_idempotent(self) -> None:
        """Retiring an already-retired model changes nothing and must not fail.

        Deliberately different from promoting a retired model. A cleanup pass that
        retires what is already retired is harmless, while promoting a retired
        version is an attempt to reuse it, which is the thing R-68 forbids.
        """
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0"))
        registry.retire("flownet@1.0.0")

        again = registry.retire("flownet@1.0.0")

        assert again.status == "retired"
        assert registry.get("flownet@1.0.0").status == "retired"

    def test_a_retired_model_cannot_move_to_staging(self) -> None:
        """The terminal state has no exit at all, not merely no promotion."""
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0"))
        registry.retire("flownet@1.0.0")

        with pytest.raises(InvalidTransition, match="terminal"):
            registry._transition("flownet@1.0.0", "staging")  # noqa: SLF001

    def test_a_retired_model_never_becomes_active_again(self) -> None:
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0"))
        registry.retire("flownet@1.0.0")

        with pytest.raises(InvalidTransition):
            registry._transition("flownet@1.0.0", "active")  # noqa: SLF001

    def test_retired_still_appears_in_the_snapshot(self) -> None:
        """Terminal is not deleted; the history has to remain readable."""
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0"))
        registry.retire("flownet@1.0.0")

        assert [info.model_id for info in registry.snapshot()] == ["flownet@1.0.0"]
        assert registry.snapshot()[0].status == "retired"


# --- status transitions -----------------------------------------------------


class TestTransitions:
    """Status is the only mutable thing, and it moves on rails."""

    def test_the_table_matches_the_documented_lifecycle(self) -> None:
        """architecture.md §5: staging | active | retired."""
        assert set(ALLOWED_TRANSITIONS) == {"staging", "active", "retired"}
        assert ALLOWED_TRANSITIONS["staging"] == frozenset({"active", "retired"})
        assert ALLOWED_TRANSITIONS["active"] == frozenset({"retired"})
        assert ALLOWED_TRANSITIONS["retired"] == frozenset()

    def test_a_staging_model_can_be_promoted(self) -> None:
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0", status="staging"))

        result = registry.promote("flownet@1.0.0")

        assert result.promoted.status == "active"
        assert result.retired is None
        assert registry.get("flownet@1.0.0").is_serving

    def test_promotion_retires_the_incumbent_in_the_same_call(self) -> None:
        """Two calls would leave a window with two active models, or none."""
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0", status="active"))
        registry.register(flow("flownet@1.1.0", status="staging"))

        result = registry.promote("flownet@1.1.0")

        assert result.promoted.model_id == "flownet@1.1.0"
        assert result.retired is not None
        assert result.retired.model_id == "flownet@1.0.0"
        assert registry.active("flow") is not None
        assert registry.active("flow").model_id == "flownet@1.1.0"

    def test_promotion_leaves_exactly_one_active_model(self) -> None:
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0", status="active"))
        registry.register(flow("flownet@1.1.0", status="staging"))
        registry.register(flow("flownet@1.2.0", status="staging"))

        registry.promote("flownet@1.1.0")
        registry.promote("flownet@1.2.0")

        actives = [info for info in registry.snapshot() if info.status == "active"]
        assert [info.model_id for info in actives] == ["flownet@1.2.0"]

    def test_promoting_an_already_active_model_retires_nothing(self) -> None:
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0", status="active"))

        result = registry.promote("flownet@1.0.0")

        assert result.retired is None
        assert registry.get("flownet@1.0.0").status == "active"

    def test_a_model_cannot_go_back_to_staging(self) -> None:
        """No path back, so a version cannot be quietly re-qualified."""
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0", status="staging"))
        registry.promote("flownet@1.0.0")

        with pytest.raises(InvalidTransition, match="cannot move to"):
            registry._transition("flownet@1.0.0", "staging")  # noqa: SLF001

    def test_promotion_does_not_cross_kinds(self) -> None:
        """FR-30: two independently versioned models must not interfere."""
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0", status="active"))
        registry.register(
            ModelInfo(
                model_id="lognet@1.0.0",
                kind="log",
                status="staging",
                sha256="c" * 64,
                loaded_at=T1,
            )
        )

        result = registry.promote("lognet@1.0.0")

        assert result.retired is None
        assert registry.get("flownet@1.0.0").status == "active"
        assert registry.get("lognet@1.0.0").status == "active"

    def test_promoting_an_unknown_model_names_it(self) -> None:
        registry = ModelRegistry()

        with pytest.raises(ModelNotLoaded, match="flownet@9.9.9"):
            registry.promote("flownet@9.9.9")


# --- content addressing -----------------------------------------------------


class TestContentAddressing:
    """R-68's other half: the address identifies the bytes."""

    def test_the_address_is_the_sha256_of_the_bytes(self) -> None:
        import hashlib

        data = b"aegis artifact bytes"

        assert content_address_bytes(data) == hashlib.sha256(data).hexdigest()

    def test_different_bytes_give_different_addresses(self) -> None:
        assert content_address_bytes(b"one") != content_address_bytes(b"two")

    def test_a_file_hashes_the_same_as_its_bytes(self, tmp_path: object) -> None:
        from pathlib import Path

        target = Path(str(tmp_path)) / "model.bin"
        payload = b"weights" * 1000
        target.write_bytes(payload)

        assert content_address(target) == content_address_bytes(payload)

    def test_a_malformed_address_is_refused(self) -> None:
        """An artifact that cannot be identified must not be registrable."""
        for bad in ("", "not-a-hash", "A" * 64, "a" * 63, "g" * 64):
            with pytest.raises(ValueError, match="content address"):
                ModelInfo(
                    model_id="flownet@1.0.0",
                    kind="flow",
                    status="active",
                    sha256=bad,
                    loaded_at=T0,
                )

    def test_verify_detects_a_changed_artifact(self, tmp_path: object) -> None:
        """What storing the address is for: spotting a swapped artifact."""
        from pathlib import Path

        target = Path(str(tmp_path)) / "model.bin"
        target.write_bytes(b"original weights")
        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0", sha256=content_address_bytes(b"original weights")))

        assert registry.verify("flownet@1.0.0", target)

        target.write_bytes(b"substituted weights")

        assert not registry.verify("flownet@1.0.0", target)

    def test_verify_reports_a_missing_artifact(self, tmp_path: object) -> None:
        from pathlib import Path

        registry = ModelRegistry()
        registry.register(flow("flownet@1.0.0"))

        with pytest.raises(FileNotFoundError):
            registry.verify("flownet@1.0.0", Path(str(tmp_path)) / "absent.bin")

    def test_info_is_immutable(self) -> None:
        """Frozen, so a caller cannot edit a registered record in place."""
        info = flow("flownet@1.0.0")

        with pytest.raises(Exception):  # noqa: B017, PT011 - frozen dataclass error type
            info.status = "retired"  # type: ignore[misc]
