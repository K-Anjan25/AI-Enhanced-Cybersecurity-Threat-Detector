"""OpenTelemetry tracing and W3C trace-context propagation (NFR-07, T-317).

The acceptance criterion for this task is a sentence about *propagation*: "a
trace ID from the ingest response appears in the alert record". So this module
does two things and deliberately no more -- it creates spans for the stages of
the pipeline, and it moves a trace context between processes.

**The propagation format is the standard one, not one of our own.** A trace that
only this service understands is a trace that stops at the first hop that is not
this service, and the value of a trace id is that the collector, the broker and
the analyst's query all agree on it. Inbound and outbound contexts are W3C
``traceparent`` (version ``00``, a 32-hex trace id and a 16-hex span id), handled
by ``opentelemetry.propagate``. All-zero ids are the standard's "invalid" and are
ignored rather than rejected: a client sending a malformed header gets a fresh
trace, because refusing an ingest batch over a broken tracing header trades data
for telemetry, which is the wrong way round.

**The SDK ships; the exporter is configuration.** Spans are recorded by
``opentelemetry.sdk.trace`` and exported through a ``SpanExporter`` that
:func:`configure_tracing` takes as an argument. The default is no exporter at
all -- the ids are still generated and propagated, which is what the pipeline and
the acceptance criterion need, and nothing is sent anywhere until a deployment
names a collector. That keeps the sandbox and the test suite free of a network
call while leaving the production path a one-line change (D-050).

**Context is carried explicitly between stages, not implicitly.** The scoring
worker and the correlator are not called from inside the ingest request: they
consume records later, in another process. They rebuild the parent context from
the trace id that travelled with the record (a Kafka header, or in-process in
tests) via :func:`context_from_traceparent`, so a child span lands on the same
trace rather than on a new one.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import (
    Span,
    SpanKind,
    format_span_id,
    format_trace_id,
)

__all__ = [
    "TRACEPARENT_HEADER",
    "configure_tracing",
    "exporter_for",
    "context_from_traceparent",
    "current_trace_id",
    "current_traceparent",
    "get_tracer",
    "span",
    "trace_id_from_traceparent",
    "traceparent_for",
]

#: The W3C header, lower-case: ASGI hands headers over lower-cased and the
#: propagator looks up exactly this key.
TRACEPARENT_HEADER = "traceparent"

_service_name = "aegis-backend"
_provider: TracerProvider | None = None
_exporter: SpanExporter | None = None


def configure_tracing(
    exporter: SpanExporter | None = None, *, service_name: str = "aegis-backend"
) -> TracerProvider:
    """Install the process's tracer provider and return it.

    Idempotent: configuring twice returns the provider already installed instead
    of adding a second one, because two providers sharing a process means half
    the spans going to each exporter. ``exporter`` is where a deployment plugs in
    its OTLP or console exporter; tests plug in an in-memory one.
    """
    global _provider, _exporter, _service_name  # noqa: PLW0603
    _service_name = service_name
    if _provider is None:
        # The resource is what tells a collector which service a span came from;
        # the SDK's default resource reports ``service.name=unknown_service`` for
        # every process, which is indistinguishable from a misconfiguration.
        _provider = TracerProvider(
            resource=Resource.create({"service.name": service_name, "service.namespace": "aegis"})
        )
        # Once per process, and only when this module made the provider: OpenTelemetry
        # refuses a second global provider, and a provider replaced mid-run would
        # silently drop spans the earlier one had already accepted.
        trace.set_tracer_provider(_provider)
    if exporter is not None and exporter is not _exporter:
        _provider.add_span_processor(SimpleSpanProcessor(exporter))
        _exporter = exporter
    return _provider


def exporter_for(endpoint: str) -> SpanExporter | None:
    """The exporter a deployment configured, or ``None`` when it configured none.

    The OTLP exporter is an optional dependency, so a deployment that sets the
    endpoint without installing it gets a named error at startup instead of a
    service that quietly exports nothing -- the failure mode where tracing looks
    configured and no span ever arrives. An empty endpoint means no exporter: the
    ids are still created and propagated, which is what the pipeline and the
    acceptance criterion need.
    """
    if not endpoint.strip():
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
    except ImportError as exc:  # pragma: no cover - depends on the installed extras
        msg = (
            "an OTLP endpoint is configured but the OTLP exporter is not installed; "
            "install aegis-backend[otlp] or unset the tracing endpoint"
        )
        raise RuntimeError(msg) from exc
    exporter: SpanExporter = OTLPSpanExporter(endpoint=endpoint)  # pragma: no cover - extra
    return exporter  # pragma: no cover - extra


def get_tracer() -> trace.Tracer:
    """The tracer for this service, creating the provider on first use."""
    if _provider is None:  # pragma: no cover - the application configures it first
        configure_tracing()
    return trace.get_tracer(_service_name)


def traceparent_for(span: Span | None = None) -> str | None:
    """The ``traceparent`` of a span, for putting on a record or a response.

    Returns ``None`` for a span that is not recording (no provider configured, or
    an invalid span), because a header carrying invented ids would make an
    unexported trace look like an exported one.
    """
    if span is None:
        return None
    span_context = span.get_span_context()
    if not span_context.is_valid:
        return None
    # The span's own flags, not a re-derived "sampled" guess: the propagation
    # libraries put more than one bit in this field, and a header that disagreed
    # with the span it describes would be a second opinion nobody asked for.
    flags = int(span_context.trace_flags) & 0xFF
    return (
        f"00-{format_trace_id(span_context.trace_id)}-"
        f"{format_span_id(span_context.span_id)}-{flags:02x}"
    )


def current_traceparent() -> str | None:
    """The ``traceparent`` of whatever span is current, or ``None``."""
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier.get(TRACEPARENT_HEADER)


def current_trace_id() -> str | None:
    """The current trace id in 32-hex form, or ``None`` when nothing is recording."""
    span_context = trace.get_current_span().get_span_context()
    return format_trace_id(span_context.trace_id) if span_context.is_valid else None


def context_from_traceparent(traceparent: str | None) -> otel_context.Context | None:
    """Rebuild a parent context from a ``traceparent`` header.

    ``None`` for a missing or malformed header: the standard's extractor already
    ignores invalid ids, so a caller that gets ``None`` starts a fresh trace.
    """
    if not traceparent:
        return None
    carrier = {TRACEPARENT_HEADER: traceparent}
    extracted = extract(carrier)
    if trace.get_current_span(extracted).get_span_context().is_valid:
        return extracted
    return None


def trace_id_from_traceparent(traceparent: str | None) -> str | None:
    """The trace id inside a ``traceparent``, or ``None`` if it is not usable."""
    context = context_from_traceparent(traceparent)
    if context is None:
        return None
    span_context = trace.get_current_span(context).get_span_context()
    return format_trace_id(span_context.trace_id)


@contextmanager
def span(
    name: str,
    *,
    parent_traceparent: str | None = None,
    kind: SpanKind | str = SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
) -> Iterator[Span]:
    """Open a span, optionally as a child of a trace id that arrived with a record.

    The parent is taken from ``parent_traceparent`` when one is given, so a stage
    that runs minutes later, in another process, still lands on the trace the
    ingest request started. Without a parent the span becomes a new trace, which
    is the honest outcome: a record with no trace context cannot be attributed to
    one.

    The span is named here and never renamed, so a caller cannot leak a
    client-supplied string into a span name.
    """
    parent = context_from_traceparent(parent_traceparent)
    tracer = get_tracer()
    with tracer.start_as_current_span(
        name,
        context=parent,
        kind=kind if isinstance(kind, SpanKind) else SpanKind(kind),
        attributes=attributes or {},
        record_exception=True,
        set_status_on_exception=True,
    ) as active:
        yield active


def duration_seconds(started: float) -> float:
    """Seconds since a :func:`time.perf_counter` reading, never negative."""
    return max(0.0, time.perf_counter() - started)
