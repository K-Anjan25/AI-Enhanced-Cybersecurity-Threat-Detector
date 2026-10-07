"""The flow read route's wire shapes (T-418, FR-52).

One response answers the traffic explorer's three panels, the same way
``GET /api/v1/overview`` answers the overview's (T-416): the series, the addresses and the
relationships are three views of one window, so they cannot disagree about the window the
way three requests could.

**Every number says what it counted.** A bucket carries its flow, byte and packet totals
*and* the alert count and mean score the series overlays; an address carries its traffic
*and* the alert counts that attach to it by address; the totals carry the window's counts
*and* the two flags that say whether the lists below them are top-Ns. A client that
rendered any of these without its qualifier would be showing a number whose meaning it
had to guess, which is what R-74 forbids.

**Nullable, not zero, where the difference matters.** A bucket no alert fell in has
``score: null`` rather than ``0.0`` (an empty bucket is not a benign one), and an address
with no alert has ``worst_severity: null`` and ``max_score: null`` rather than empty
strings. ``source`` is a literal rather than free text so a client can switch on it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "FlowAggregateOut",
    "FlowBucketOut",
    "FlowEdgeOut",
    "FlowEntityOut",
    "FlowFiltersOut",
    "FlowTotalsOut",
    "FlowWindowOut",
]


class FlowWindowOut(BaseModel):
    """The window the read answered about, echoed so a client never guesses it."""

    model_config = ConfigDict(frozen=True)

    start: datetime = Field(description="Inclusive lower bound of the window (R-34).")
    end: datetime = Field(description="Exclusive upper bound of the window (R-34).")
    hours: float = Field(description="The window's width in hours, for display.")


class FlowFiltersOut(BaseModel):
    """The narrowing the read applied, so a filter is never invisible on the wire."""

    model_config = ConfigDict(frozen=True)

    protocol: str | None = Field(
        default=None, description="Protocol the read was narrowed to, or null for all."
    )
    direction: str | None = Field(
        default=None, description="Direction the read was narrowed to, or null for all."
    )


class FlowBucketOut(BaseModel):
    """One point of the volume series, with the alert overlay it is drawn against."""

    model_config = ConfigDict(frozen=True)

    start: datetime = Field(description="Inclusive lower bound of the bucket.")
    flows: int = Field(description="Flow records in the bucket.")
    bytes: int = Field(description="Bytes those records carried.")
    packets: int = Field(description="Packets those records carried.")
    alerts: int = Field(description="Alerts raised in the bucket, joined on its instant.")
    score: float | None = Field(
        default=None,
        description=(
            "Mean composite score of those alerts, or null when the bucket held none. "
            "Null rather than zero: an empty bucket is not a benign one."
        ),
    )


class FlowEntityOut(BaseModel):
    """One address's share of the window, and the alerts that attach to it."""

    model_config = ConfigDict(frozen=True)

    ip: str = Field(description="The address, as it appeared on the wire.")
    flows: int = Field(description="Records in which it was an end.")
    bytes: int = Field(description="Bytes those records carried.")
    packets: int = Field(description="Packets those records carried.")
    inbound: int = Field(description="Records in which it was the destination.")
    outbound: int = Field(description="Records in which it was the source.")
    first_seen: datetime | None = Field(default=None, description="Oldest record, in window.")
    last_seen: datetime | None = Field(default=None, description="Newest record, in window.")
    alerts: int = Field(
        default=0,
        description="Alerts in the window whose entity value is this address.",
    )
    open_alerts: int = Field(default=0, description="How many of them are still open.")
    worst_severity: str | None = Field(
        default=None, description="Most serious band among them, or null for none."
    )
    max_score: float | None = Field(
        default=None, description="Highest score among them, or null for none."
    )


class FlowEdgeOut(BaseModel):
    """One directional relationship: two addresses that exchanged traffic."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(description="Source address.")
    target: str = Field(description="Destination address.")
    flows: int = Field(description="Records between them, in that direction.")
    bytes: int = Field(description="Bytes those records carried.")


class FlowTotalsOut(BaseModel):
    """The window's counts, and what each cap did to the lists."""

    model_config = ConfigDict(frozen=True)

    flows: int = Field(description="Flow records in the window -- every one of them.")
    bytes: int = Field(description="Bytes they carried.")
    packets: int = Field(description="Packets they carried.")
    nodes: int = Field(description="Distinct addresses in the window.")
    edges: int = Field(description="Distinct directional pairs in the window.")
    nodes_capped: bool = Field(
        description="True when more addresses were seen than the entity list holds."
    )
    edges_capped: bool = Field(
        description="True when more relationships were seen than the edge list holds."
    )
    untracked_address_flows: int = Field(
        default=0,
        description=(
            "Records the in-process rollup could not attribute to an address because it "
            "was full. They are in ``flows`` either way; always 0 for a store."
        ),
    )
    untracked_pair_flows: int = Field(
        default=0,
        description=(
            "Records the in-process rollup could not attribute to a pair because it was "
            "full. They are in ``flows`` either way; always 0 for a store."
        ),
    )


class FlowAggregateOut(BaseModel):
    """One window's traffic: the series, the addresses, the relationships and the caveats."""

    model_config = ConfigDict(frozen=True)

    window: FlowWindowOut = Field(description="The window these numbers describe.")
    bucket_minutes: int = Field(description="Resolution of the series.")
    source: Literal["store", "rollup"] = Field(
        description="Which read model answered: the flow store or the in-process rollup."
    )
    filters: FlowFiltersOut = Field(description="The narrowing applied to the read.")
    series: list[FlowBucketOut] = Field(description="Volume per bucket, oldest first.")
    entities: list[FlowEntityOut] = Field(description="Addresses, busiest first, capped.")
    edges: list[FlowEdgeOut] = Field(description="Relationships, heaviest first, capped.")
    totals: FlowTotalsOut = Field(description="The window's counts and the caps' effect.")
    caveats: list[str] = Field(
        description="What a reader must know about these numbers, in the source's words."
    )
