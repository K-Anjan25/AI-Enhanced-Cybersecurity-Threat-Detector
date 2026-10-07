"""Which flow read model answers, and what a reader must know about it (T-418).

The same shape T-419 gave the logs: a protocol both sources implement, a wrapper for the
in-process one that carries the sentence explaining *why* it is the one answering, and a
caveat builder so the numbers and the sentences that qualify them are produced together.
The endpoint holds one object and cannot tell the two apart except by asking
:attr:`FlowSource.name`, which is exactly the point -- a deployment decides where its
traffic is read from, and the screen learns which one it got.

**Why a rollup is the in-process answer, and what that costs.** A buffer of ``flow@1``
records would be a memory leak with a retention window for a lid at 5,000 flows/s, and
the three questions the explorer asks are totals, so the in-process source keeps totals.
The price is granularity: :class:`RollupFlowSource` is minute-grained, so a window that
starts or ends inside a minute includes that whole minute, and the caveats say so. The
store, grouping in SQL, is exact.

**The reasons are sentences, not codes.** ``store_requested`` decides the source once, at
startup, from ``AEGIS_FLOW_STORE`` and whether a database URL was *named* rather than
inherited from the default; the two ways a deployment can end up on the rollup produce
two different sentences, because "you turned it off" and "you never configured one" call
for different actions from whoever reads the screen.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.core.config import LogStoreMode
from app.schemas.ingest import FlowRecordIn
from app.services.flow_read_model import (
    DEFAULT_FLOW_BUCKET_MINUTES,
    DEFAULT_FLOW_EDGE_LIMIT,
    DEFAULT_FLOW_ENTITY_LIMIT,
    FLOW_ROLLUP_MINUTES,
    FlowAggregate,
    FlowFilters,
    FlowTotals,
    FlowWindow,
    InProcessFlowRollup,
)

__all__ = [
    "FlowSource",
    "RollupFlowSource",
    "flow_caveats",
    "flow_rollup_reason",
]


#: The sentence a rollup-backed deployment's reads carry, by mode. Only two cases reach
#: it: a deployment that turned the flow store off, and one that never named a database.
_ROLLUP_REASON = {
    LogStoreMode.OFF: (
        "This deployment counts traffic from its own in-process rollup because "
        "AEGIS_FLOW_STORE is off. The store exists (T-418): set AEGIS_FLOW_STORE=on to "
        "count stored flows instead."
    ),
    LogStoreMode.AUTO: (
        "This deployment counts traffic from its own in-process rollup because no "
        "database URL is named. Set AEGIS_DATABASE_URL to the deployment's PostgreSQL "
        "(and run alembic upgrade head) to count stored flows instead (T-418)."
    ),
}


def flow_rollup_reason(mode: LogStoreMode) -> str:
    """Why a rollup is answering under ``mode``, as a sentence a screen can render."""
    return _ROLLUP_REASON.get(
        mode,
        "This deployment counts traffic from its own in-process rollup because the flow "
        "store is not enabled.",
    )


class FlowSource(Protocol):
    """What the flow route needs from whichever read model answers.

    ``name`` is on the protocol rather than only on the response because the route puts
    it there *from here*: a source that could not say what it is would be a source whose
    reads are indistinguishable from the other one's (T-419's rule, applied to traffic).
    """

    #: ``"store"`` or ``"rollup"``, and what the response's ``source`` field carries.
    name: str

    @property
    def max_span_seconds(self) -> float:
        """The widest window this source will answer, in seconds."""
        ...

    async def append(self, records: Sequence[FlowRecordIn]) -> int:
        """Keep a batch of accepted flow records, returning how many were kept."""
        ...

    async def summary(
        self,
        window: FlowWindow,
        *,
        bucket_minutes: int = DEFAULT_FLOW_BUCKET_MINUTES,
        entity_limit: int = DEFAULT_FLOW_ENTITY_LIMIT,
        edge_limit: int = DEFAULT_FLOW_EDGE_LIMIT,
        filters: FlowFilters | None = None,
    ) -> FlowAggregate:
        """Aggregate the window into the explorer's three panels."""
        ...


class RollupFlowSource:
    """The in-process rollup, behind the same interface as the store.

    The rollup's work is dict arithmetic -- microseconds, no I/O -- so this wrapper calls
    it inline rather than pretending to be asynchronous. It is ``async def`` because the
    interface is, and it carries in ``reason`` why this deployment counts traffic from
    memory.
    """

    __slots__ = ("_reason", "_rollup")

    name = "rollup"

    def __init__(self, rollup: InProcessFlowRollup, *, reason: str) -> None:
        """Wrap one rollup, with the sentence its reads carry."""
        self._rollup = rollup
        self._reason = reason

    @property
    def rollup(self) -> InProcessFlowRollup:
        """The wrapped rollup, for tests and for the readiness probe."""
        return self._rollup

    @property
    def reason(self) -> str:
        """Why this deployment is counting traffic from memory."""
        return self._reason

    @property
    def max_span_seconds(self) -> float:
        """A rollup's widest window is its own retention."""
        return self._rollup.max_age_seconds

    async def append(self, records: Sequence[FlowRecordIn]) -> int:
        """Count the batch into the rollup."""
        return self._rollup.append(records)

    async def summary(
        self,
        window: FlowWindow,
        *,
        bucket_minutes: int = DEFAULT_FLOW_BUCKET_MINUTES,
        entity_limit: int = DEFAULT_FLOW_ENTITY_LIMIT,
        edge_limit: int = DEFAULT_FLOW_EDGE_LIMIT,
        filters: FlowFilters | None = None,
    ) -> FlowAggregate:
        """Aggregate the window from the retained minutes."""
        return self._rollup.summary(
            window,
            bucket_minutes=bucket_minutes,
            entity_limit=entity_limit,
            edge_limit=edge_limit,
            filters=filters,
        )


def flow_caveats(
    *,
    source_name: str,
    window: FlowWindow,
    totals: FlowTotals,
    listed_nodes: int,
    listed_edges: int,
    reason: str | None = None,
    retained_from: datetime | None = None,
    stored_ever: bool | None = None,
    filters: FlowFilters | None = None,
) -> list[str]:
    """What a reader must know to read a flow aggregate honestly (R-70, R-74).

    Built where the numbers are, so a screen cannot render a count without the sentence
    that qualifies it: which source answered, what that source cannot see, why the window
    is empty when it is, and what each cap did to the lists.

    Args:
        source_name: ``"store"`` or ``"rollup"``.
        window: the window that was read.
        totals: the counts the read produced, caps included.
        listed_nodes: how many addresses the response listed.
        listed_edges: how many relationships it listed.
        reason: the rollup's own "why this source" sentence, when one is answering.
        retained_from: the oldest minute the rollup still holds.
        stored_ever: whether anything has ever been stored (``None`` when unknown).
        filters: the narrowing the read applied, repeated back when it removed rows.

    Returns:
        The sentences, in the order a reader needs them: the permanent shape of the
        source first, then what this particular read could or could not do.
    """
    chosen = filters or FlowFilters()
    caveats: list[str] = []

    if source_name == "store":
        caveats.append(
            "These numbers are counted from the flow store (the flow_events table), so "
            "they survive a restart and a second worker counts the same traffic. Only "
            "accepted flow records are in it."
        )
    else:
        caveats.append(
            "These numbers are counted from this process's own in-process rollup: the "
            f"last {FLOW_ROLLUP_MINUTES} minutes of accepted flow records, kept as "
            "per-minute totals. It is not a store: a restart, a second worker or a "
            "minute older than that is not in it."
        )
        # The granularity is the price of the rollup, and it belongs where the numbers
        # are rather than in a comment a screen never reads.
        caveats.append(
            "The rollup is minute-grained: a window that starts or ends inside a minute "
            "includes that whole minute. A stored read is exact to the instant."
        )
        if reason is not None:
            caveats.append(reason)

    # The score line is alert-derived and the join is by address: two facts a reader
    # cannot recover from the numbers themselves.
    caveats.append(
        "A flow record carries no score or severity: a bucket's score is the mean alert "
        "score of the alerts raised in it, and an address carries alert counts only where "
        "an alert's entity value is that address (flow-modality detections are keyed by "
        "source address). Traffic with no alert is counted, and shows no score."
    )

    if totals.flows == 0:
        if stored_ever is False or (source_name == "rollup" and retained_from is None):
            caveats.append(
                "Nothing has been counted yet, so this window is empty because there is "
                "nothing to show rather than because nothing matched."
            )
        elif retained_from is not None and window.end <= retained_from:
            caveats.append(
                f"No flow is held at or before {window.end.isoformat()}: the traffic this "
                f"source still counts starts at {retained_from.isoformat()}."
            )
        else:
            caveats.append(
                "No accepted flow record falls inside this window. The window is answered "
                "about the traffic that was ingested, not about the network."
            )
    elif chosen.protocol is not None or chosen.direction is not None:
        caveats.append(
            "These counts are narrowed by the filter shown with them: traffic the filter "
            "excluded is in no number on this screen."
        )

    if totals.nodes_capped:
        caveats.append(
            f"The entity list shows the busiest {listed_nodes} of {totals.nodes} "
            "addresses; the rest are counted in the totals, not listed."
        )
    if totals.edges_capped:
        caveats.append(
            f"The edge list shows the heaviest {listed_edges} of {totals.edges} "
            "relationships; the rest are counted in the totals, not listed."
        )
    if totals.untracked_address_flows > 0:
        caveats.append(
            f"{totals.untracked_address_flows} accepted records were not attributed to an "
            "address: this process's rollup was full, so the per-address breakdown is "
            "partial while the totals are not."
        )
    if totals.untracked_pair_flows > 0:
        caveats.append(
            f"{totals.untracked_pair_flows} accepted records were not attributed to a "
            "pair: this process's rollup was full, so the edge breakdown is partial while "
            "the totals are not."
        )
    return caveats
