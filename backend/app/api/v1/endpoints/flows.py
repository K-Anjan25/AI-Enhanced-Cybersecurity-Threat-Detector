"""``GET /api/v1/flows`` -- one window of traffic, counted (T-418, FR-52).

The traffic explorer asked for this and got an alert list: volume was the raw-record
count the alerts carried, entities were entity ids, and edges were shared correlation
traces, so every number on the screen was a statement about the *alerted* subset of the
traffic. This route counts the traffic instead -- from the flow store when the deployment
has one, from the in-process rollup otherwise -- and joins the alert side onto it by the
one key the two sides share.

**Why the join lives here and not in the read model.** A ``flow@1`` record carries no
score, no severity and no entity. Those belong to alerts, and the alert store already
knows them: ``alert_store.aggregate`` is the same complete-window tally the overview uses
(T-416), and the entity registry turns each ``entity_id`` into the ``(kind, value)`` pair
the pipeline keyed it by -- which for flow-modality detections is the source address. So
the traffic numbers come from the flow read model and the alert numbers come from the
alert read model, and the endpoint is where they meet. A read model that invented a score
would be making a claim the pipeline never made.

**The score overlay is the same join, on the time axis.** A bucket's ``score`` is the mean
score of the alerts raised in that bucket, or ``null`` when none was: the series draws a
gap in the score line rather than a line along the floor, because an empty bucket is not a
benign one.

**One rule from the log routes, unchanged:** a window wider than the answering source can
read is refused with the bound in the source's own seconds, rather than answered with an
empty half a reader would take for quietness.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.deps import alert_store, entity_registry, flow_source
from app.auth.rbac import Capability, require
from app.db.repository import TimeRange
from app.schemas.flows import (
    FlowAggregateOut,
    FlowBucketOut,
    FlowEdgeOut,
    FlowEntityOut,
    FlowFiltersOut,
    FlowTotalsOut,
    FlowWindowOut,
)
from app.services.flow_read_model import (
    DEFAULT_FLOW_BUCKET_MINUTES,
    DEFAULT_FLOW_EDGE_LIMIT,
    DEFAULT_FLOW_ENTITY_LIMIT,
    FLOW_BUCKET_MINUTES_MAX,
    FLOW_EDGE_LIMIT_MAX,
    FLOW_ENTITY_LIMIT_MAX,
    FlowFilters,
    FlowWindow,
)
from app.services.flow_source import FlowSource, flow_caveats
from app.services.flow_store import FlowStoreUnavailable
from app.services.overview import ENTITY_LIMIT_MAX as ALERT_ENTITY_LIMIT_MAX

router = APIRouter(prefix="/api/v1", tags=["flows"])


@router.get(
    "/flows",
    response_model=FlowAggregateOut,
    summary="Count one window of traffic: volume, addresses and relationships (FR-52)",
    dependencies=[require(Capability.READ)],
)
async def read_flows(
    request: Request,
    start: str = Query(description="Inclusive lower bound, ISO-8601 with an offset."),
    end: str = Query(description="Exclusive upper bound, ISO-8601 with an offset."),
    bucket_minutes: int = Query(
        default=DEFAULT_FLOW_BUCKET_MINUTES,
        ge=1,
        le=FLOW_BUCKET_MINUTES_MAX,
        description="The volume series' resolution.",
    ),
    entity_limit: int = Query(
        default=DEFAULT_FLOW_ENTITY_LIMIT,
        ge=1,
        le=FLOW_ENTITY_LIMIT_MAX,
        description="How many addresses the list holds. The counts are unaffected.",
    ),
    edge_limit: int = Query(
        default=DEFAULT_FLOW_EDGE_LIMIT,
        ge=1,
        le=FLOW_EDGE_LIMIT_MAX,
        description="How many relationships the list holds. The counts are unaffected.",
    ),
    protocol: str | None = Query(
        default=None, description="Narrow to one protocol (tcp, udp, icmp)."
    ),
    direction: str | None = Query(
        default=None, description="Narrow to one direction (inbound, outbound, internal)."
    ),
) -> FlowAggregateOut:
    """Count one bounded window of accepted flow records.

    ``start`` and ``end`` are required for the same reason the alert list's are (R-34):
    a read with no time predicate is the unbounded scan the rule names, and a generous
    default is how one ships.

    ``entity_limit`` and ``edge_limit`` cap a *list*, never a count: ``totals`` covers
    every record in the window, and when more addresses or pairs were seen than the list
    holds, ``nodes_capped``/``edges_capped`` say so and the caveats name both numbers.
    """
    try:
        span = TimeRange(start=datetime.fromisoformat(start), end=datetime.fromisoformat(end))
    except ValueError as exc:
        # A naive or inverted range, or one wider than the R-34 span limit.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    chosen = _filters(protocol, direction)
    source = flow_source(request)
    if span.span.total_seconds() > source.max_span_seconds:
        # The bound is stated in the source's own seconds, like the log routes': a
        # client that is refused must not have to guess which source refused it or why.
        raise HTTPException(
            status_code=400,
            detail=(
                f"the {source.name} answers at most "
                f"{source.max_span_seconds:g} seconds of traffic; this window spans "
                f"{span.span.total_seconds():g}"
            ),
        )

    window = FlowWindow(start=span.start, end=span.end)
    try:
        traffic = await source.summary(
            window,
            bucket_minutes=bucket_minutes,
            entity_limit=entity_limit,
            edge_limit=edge_limit,
            filters=chosen,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FlowStoreUnavailable as exc:
        # A deployment that configured a store and cannot reach it must say so, not draw
        # an empty graph: an empty window reads as a quiet network, which is the one
        # thing a traffic screen must never say when it does not know (R-70). The log
        # routes answer 503 for the same reason.
        raise HTTPException(
            status_code=503, detail=f"the flow store could not answer: {exc}"
        ) from exc

    alerts = _alert_view(request, span, bucket_minutes=bucket_minutes)
    retained_from = getattr(getattr(source, "rollup", None), "retained_from", None)
    stored_ever = await _stored_ever(source)

    return FlowAggregateOut(
        window=FlowWindowOut(
            start=window.start,
            end=window.end,
            hours=window.span_seconds / 3_600,
        ),
        bucket_minutes=bucket_minutes,
        source=source.name,  # the protocol's two names are the Literal's two values
        filters=FlowFiltersOut(protocol=chosen.protocol, direction=chosen.direction),
        series=[
            FlowBucketOut(
                start=point.start,
                flows=point.flows,
                bytes=point.bytes,
                packets=point.packets,
                alerts=alerts.scores.get(point.start, (0, None))[0],
                score=alerts.scores.get(point.start, (0, None))[1],
            )
            for point in traffic.series
        ],
        entities=[
            FlowEntityOut(
                ip=node.ip,
                flows=node.flows,
                bytes=node.bytes,
                packets=node.packets,
                inbound=node.inbound,
                outbound=node.outbound,
                first_seen=node.first_seen,
                last_seen=node.last_seen,
                **_alert_fields(alerts, node.ip),
            )
            for node in traffic.entities
        ],
        edges=[
            FlowEdgeOut(source=edge.source, target=edge.target, flows=edge.flows, bytes=edge.bytes)
            for edge in traffic.edges
        ],
        totals=FlowTotalsOut(
            flows=traffic.totals.flows,
            bytes=traffic.totals.bytes,
            packets=traffic.totals.packets,
            nodes=traffic.totals.nodes,
            edges=traffic.totals.edges,
            nodes_capped=traffic.totals.nodes_capped,
            edges_capped=traffic.totals.edges_capped,
            untracked_address_flows=traffic.totals.untracked_address_flows,
            untracked_pair_flows=traffic.totals.untracked_pair_flows,
        ),
        caveats=flow_caveats(
            source_name=source.name,
            window=window,
            totals=traffic.totals,
            listed_nodes=len(traffic.entities),
            listed_edges=len(traffic.edges),
            reason=getattr(source, "reason", None),
            retained_from=retained_from,
            stored_ever=stored_ever,
            filters=chosen,
        ),
    )


def _filters(protocol: str | None, direction: str | None) -> FlowFilters:
    """Validate the two narrowing parameters, or refuse the read.

    Raises:
        HTTPException: 400, naming the value and the ones that are understood -- a
            silently ignored filter is a screen showing traffic the caller excluded.
    """
    allowed_protocols = {"tcp", "udp", "icmp"}
    allowed_directions = {"inbound", "outbound", "internal"}
    if protocol is not None and protocol not in allowed_protocols:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown protocol {protocol!r}; expected one of "
                f"{', '.join(sorted(allowed_protocols))}"
            ),
        )
    if direction is not None and direction not in allowed_directions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown direction {direction!r}; expected one of "
                f"{', '.join(sorted(allowed_directions))}"
            ),
        )
    return FlowFilters(protocol=protocol, direction=direction)


class _AlertView:
    """The alert side of the join: scores per bucket, and each address's alerts.

    Nothing here reads a flow: it is the alert store's own complete-window aggregate,
    reduced to the two lookups the response needs.
    """

    __slots__ = ("by_ip", "scores")

    def __init__(
        self,
        *,
        scores: dict[datetime, tuple[int, float | None]],
        by_ip: dict[str, tuple[int, int, str | None, float | None]],
    ) -> None:
        """Hold the two lookups."""
        self.scores = scores
        self.by_ip = by_ip


def _alert_view(request: Request, span: TimeRange, *, bucket_minutes: int) -> _AlertView:
    """Aggregate the window's alerts and index them the way the join needs them.

    One aggregate for both lookups: the same tally that fills the buckets' scores also
    carries each entity's alerts, so the second question costs nothing extra. Entities are
    resolved through the registry -- one lookup per tallied entity, not per alert -- and
    an alert whose entity value is not an address on the screen simply does not attach
    (the caveat says why: flow-modality detections are keyed by source address).
    """
    registry = entity_registry(request)
    summary = alert_store(request).aggregate(
        span,
        bucket_minutes=bucket_minutes,
        entity_limit=ALERT_ENTITY_LIMIT_MAX,
        family_limit=1,
    )
    scores: dict[datetime, tuple[int, float | None]] = {
        point.start: (point.total, point.score) for point in summary.points
    }
    by_ip: dict[str, tuple[int, int, str | None, float | None]] = {}
    for tally in summary.entities:
        ref = registry.ref(tally.entity_id)
        if ref is None:
            continue
        _kind, value = ref
        by_ip[value] = (
            tally.alerts,
            tally.open_alerts,
            tally.worst_severity,
            tally.max_score,
        )
    return _AlertView(scores=scores, by_ip=by_ip)


def _alert_fields(view: _AlertView, ip: str) -> dict[str, object]:
    """One address's alert fields, defaulted where the join found nothing."""
    tally = view.by_ip.get(ip)
    if tally is None:
        return {"alerts": 0, "open_alerts": 0, "worst_severity": None, "max_score": None}
    alerts, open_alerts, worst, max_score = tally
    return {
        "alerts": alerts,
        "open_alerts": open_alerts,
        "worst_severity": worst,
        "max_score": max_score,
    }


async def _stored_ever(source: FlowSource) -> bool | None:
    """Whether anything has ever been counted, when the source can be asked cheaply.

    The store answers from its cached coverage -- a whole-table aggregate it would rather
    not run per read -- and the rollup knows from whether it has ever held a minute.
    ``None`` means "not known", and the caveats then say nothing about the store rather
    than guessing about it. A store that cannot answer is treated as unknown: the read
    itself would have failed before this mattered, and a coverage failure must not turn a
    successful read into a 500.
    """
    coverage = getattr(source, "coverage", None)
    if coverage is not None:
        try:
            return not (await coverage()).empty
        except FlowStoreUnavailable:
            return None
    rollup = getattr(source, "rollup", None)
    if rollup is not None:
        return rollup.retained_from is not None
    return None
