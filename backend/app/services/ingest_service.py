"""Batch ingest: split NDJSON, validate each record, report every failure.

FR-04 says reject with a per-record error list and never fail the whole batch.
The invariant that makes "no partial batch is silently dropped" checkable is
arithmetic rather than a promise: ``received == accepted + rejected``, and one
error entry per rejected record. ``tests/test_ingest.py`` asserts both, so a
record dropped without an error entry fails the suite instead of vanishing.

Batch-level failures are different and are meant to fail the whole request. An
oversized batch is not a per-record problem -- there is no record to attribute
it to -- so it returns 413 rather than a list of 1,001 errors.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.ingest import IngestResponse, RecordError

__all__ = ["BatchTooLarge", "UnsupportedMediaType", "ingest_batch", "split_ndjson"]

_T = TypeVar("_T", bound=BaseModel)


class BatchTooLarge(ValueError):
    """The batch exceeds the per-request record limit (FR-01, FR-02)."""

    def __init__(self, received: int, limit: int) -> None:
        """Report both numbers so the caller can split the batch."""
        super().__init__(f"batch of {received} records exceeds the limit of {limit}")
        self.received = received
        self.limit = limit


class UnsupportedMediaType(ValueError):
    """The body is neither NDJSON nor a JSON array."""


def split_ndjson(body: bytes) -> tuple[list[tuple[int, object]], list[RecordError]]:
    """Split an NDJSON body into ``(index, record)`` pairs plus parse errors.

    The index is the line number in the original body, and it is carried
    through rather than recomputed, because dropping an unparseable line would
    otherwise shift every subsequent record's reported position. A client
    told "record 7 is bad" must be able to find record 7.

    A line that is not valid JSON becomes an error and the remaining lines
    still parse -- FR-04 forbids failing the whole batch over one bad record.
    Blank lines are skipped, since a trailing newline at the end of a batch is
    not a malformed record.
    """
    parsed: list[tuple[int, object]] = []
    errors: list[RecordError] = []
    for index, raw in enumerate(body.splitlines()):
        line = raw.strip()
        if not line:
            continue
        try:
            parsed.append((index, json.loads(line)))
        except json.JSONDecodeError as exc:
            errors.append(
                RecordError(
                    index=index,
                    stage="parse",
                    message=f"line is not valid JSON: {exc.msg}",
                )
            )
    return parsed, errors


def _as_records(
    body: bytes, content_type: str
) -> tuple[list[tuple[int, object]], list[RecordError]]:
    """Return the batch as indexed records, accepting NDJSON or a JSON array."""
    if "application/x-ndjson" in content_type or "application/ndjson" in content_type:
        return split_ndjson(body)
    try:
        document = json.loads(body) if body.strip() else []
    except json.JSONDecodeError as exc:
        msg = f"body is not valid JSON: {exc.msg}"
        raise UnsupportedMediaType(msg) from exc
    if isinstance(document, list):
        return list(enumerate(document)), []
    if isinstance(document, dict):
        # A single object is a batch of one, which is what a client sending one
        # record without wrapping it in an array expects.
        return [(0, document)], []
    msg = "body must be a JSON array or an NDJSON stream"
    raise UnsupportedMediaType(msg)


def ingest_batch(
    body: bytes,
    model: type[_T],
    *,
    limit: int,
    content_type: str = "application/json",
) -> tuple[IngestResponse, list[_T]]:
    """Validate a batch and report every failure without dropping a record.

    Returns the response and the accepted records. Every record in the batch
    appears in exactly one of the two, which is what makes "no partial batch is
    silently dropped" a checkable property rather than an intention.
    """
    indexed, parse_errors = _as_records(body, content_type)
    received = len(indexed) + len(parse_errors)
    if received > limit:
        raise BatchTooLarge(received, limit)

    accepted: list[_T] = []
    errors: list[RecordError] = list(parse_errors)
    rejected: set[int] = {e.index for e in parse_errors}

    for index, payload in indexed:
        try:
            accepted.append(model.model_validate(payload))
        except ValidationError as exc:
            rejected.add(index)
            # Every error pydantic reports becomes one entry, so a record with
            # three bad fields explains all three rather than only the first.
            for err in exc.errors():
                field = ".".join(str(part) for part in err["loc"]) or None
                errors.append(
                    RecordError(index=index, stage="validation", message=err["msg"], field=field)
                )

    response = IngestResponse(
        received=received,
        accepted=len(accepted),
        rejected=len(rejected),
        errors=errors,
    )
    return response, accepted


def count_records(body: Sequence[object]) -> int:
    """The number of records in an already-split batch."""
    return len(body)
