"""Tests for the model registry (R-68: immutable, no implicit latest)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aegis_ml.registry.model_registry import ModelInfo, ModelNotLoaded, ModelRegistry

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 6, 9, 30, tzinfo=UTC)


def flow(model_id: str, status: str = "active", loaded_at: datetime = T0) -> ModelInfo:
    return ModelInfo(model_id=model_id, kind="flow", status=status, loaded_at=loaded_at)  # type: ignore[arg-type]


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


def test_duplicate_id_is_rejected() -> None:
    """Versions are immutable; silently overwriting one would hide a rollback."""
    registry = ModelRegistry()
    registry.register(flow("flownet@1.0.0"))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(flow("flownet@1.0.0"))


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
    registry.register(ModelInfo(model_id="lognet@1.0.0", kind="log", status="active", loaded_at=T1))

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
