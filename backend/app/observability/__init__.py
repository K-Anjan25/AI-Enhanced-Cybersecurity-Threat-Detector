"""Observability: Prometheus metrics and OpenTelemetry traces (NFR-07, T-317).

Two modules, both about the *system's* view of itself rather than about the data
it holds:

* :mod:`app.observability.metrics` -- the counters, gauges and histograms a
  Prometheus scrape reads, plus the label sets they are allowed to carry.
* :mod:`app.observability.tracing` -- span creation and W3C trace-context
  propagation, so one trace id survives from an ingest request to the alert
  record it caused.

Neither module imports the HTTP layer, so the pipeline stages can instrument
themselves without depending on FastAPI (R-15).
"""

from __future__ import annotations

__all__: list[str] = []
