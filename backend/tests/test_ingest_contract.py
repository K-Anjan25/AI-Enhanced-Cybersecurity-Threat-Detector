"""The backend wire models must not drift from the schema of record (FR-04).

``aegis_ml.data.records`` defines ``flow@1`` and ``log@1``. The backend
duplicates them so the API process does not import the ML package, and
duplication that is allowed to drift is worse than coupling: a field added to
one side and not the other means records the API accepts that nothing
downstream can read, or records it rejects that it should accept.

So the two are compared field for field. If ``flow@1`` is revised, this fails
until both sides move together -- which is the point, since ``flow@1`` must
never be edited in place.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from app.schemas.ingest import FlowRecordIn, LogRecordIn

_ML_SERVICE = Path(__file__).resolve().parents[2] / "ml-service"


@pytest.fixture(scope="module")
def records_module() -> Any:
    """Import aegis_ml.data.records, which needs only pydantic."""
    if str(_ML_SERVICE) not in sys.path:
        sys.path.insert(0, str(_ML_SERVICE))
    from aegis_ml.data import records

    return records


def test_flow_fields_match_exactly(records_module: Any) -> None:
    assert set(FlowRecordIn.model_fields) == set(records_module.FlowRecord.model_fields)


def test_log_fields_match_exactly(records_module: Any) -> None:
    assert set(LogRecordIn.model_fields) == set(records_module.LogRecord.model_fields)


def test_required_fields_match(records_module: Any) -> None:
    """A field optional on one side and required on the other is a real break."""
    for ours, theirs in (
        (FlowRecordIn, records_module.FlowRecord),
        (LogRecordIn, records_module.LogRecord),
    ):
        ours_required = {n for n, f in ours.model_fields.items() if f.is_required()}
        theirs_required = {n for n, f in theirs.model_fields.items() if f.is_required()}
        assert ours_required == theirs_required, ours.__name__


def test_field_annotations_match(records_module: Any) -> None:
    """Compared as strings so enum identity across packages does not matter."""
    for ours, theirs in (
        (FlowRecordIn, records_module.FlowRecord),
        (LogRecordIn, records_module.LogRecord),
    ):
        for name in ours.model_fields:
            ours_ann = str(ours.model_fields[name].annotation)
            theirs_ann = str(theirs.model_fields[name].annotation)
            # The enum types are distinct classes in each package, so compare
            # the shape rather than the class.
            normalised = ours_ann.replace("app.schemas.ingest.", "").replace(
                "aegis_ml.data.records.", ""
            )
            assert normalised == theirs_ann.replace(
                "aegis_ml.data.records.", ""
            ), f"{ours.__name__}.{name}: {ours_ann} != {theirs_ann}"


def test_both_sides_forbid_extra_fields(records_module: Any) -> None:
    """Extra="forbid" is what makes an unknown field an error instead of noise."""
    for model in (
        FlowRecordIn,
        LogRecordIn,
        records_module.FlowRecord,
        records_module.LogRecord,
    ):
        assert model.model_config.get("extra") == "forbid", model.__name__


def test_schema_versions_agree(records_module: Any) -> None:
    assert FlowRecordIn.model_fields["schema_version"].default == (
        records_module.SCHEMA_VERSION_FLOW
    )
    assert LogRecordIn.model_fields["schema_version"].default == (records_module.SCHEMA_VERSION_LOG)


def test_enum_values_agree(records_module: Any) -> None:
    """Wire values are what crosses the boundary, not the Python names."""
    from app.schemas.ingest import Direction, LogLevel, Protocol

    assert [m.value for m in Protocol] == [m.value for m in records_module.Protocol]
    assert [m.value for m in Direction] == [m.value for m in records_module.Direction]
    assert [m.value for m in LogLevel] == [m.value for m in records_module.LogLevel]
