"""Wire models for the log tail read model (T-407, design.md §4.5).

Four shapes, deliberately separate:

* :class:`LogLineOut` is one raw line as ``log@1`` carried it — minus the training
  ``label``, which is not a property of production traffic and has no business on a
  screen.
* :class:`LogClusterOut` is the fold design.md §4.5 asks for: identical lines become
  one row with a count, the instants it spans, the levels that appeared, the hosts and
  services that produced it, the newest line's sample and parameters, and the ``key``
  that expands it.
* :class:`LogTailOut` and :class:`LogLinesOut` carry the retention *with* the rows.
  A bounded tail that did not say how far back it reached would be read as a complete
  log (R-70), so ``retained_from``/``retained_to``/``dropped_lines`` are fields rather
  than documentation, and ``caveats`` carries the sentences a panel renders.

``worst_level`` is a **level**, not an anomaly score. design.md §4.5 colours anomalous
templates; no log model is served in this build, so the explorer highlights the worst
level a cluster reached and says that is what it is (T-419 covers the scored version).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.ingest import LogLevel

__all__ = [
    "LogClusterOut",
    "LogLinesOut",
    "LogLineOut",
    "LogTailOut",
]


class LogLineOut(BaseModel):
    """One raw log line, with the cluster key the server computed for it."""

    timestamp: datetime = Field(description="When the line was emitted, UTC.")
    host: str = Field(description="Host that emitted the line.")
    service: str = Field(description="Service or component that emitted it.")
    level: LogLevel = Field(description="Level as log@1 defines it.")
    message: str = Field(description="The raw line, parameters and all.")
    template_id: str | None = Field(
        default=None,
        description="Template the collector mined for this line, when it sent one.",
    )
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Named values the template was filled with, when the collector sent them.",
    )
    key: str = Field(description="Cluster this line folds into: a template id or a message digest.")


class LogClusterOut(BaseModel):
    """One row of the fold: a template (or a repeated message) with its count."""

    key: str = Field(description="Stable id for this cluster; pass it back to expand the rows.")
    template_id: str | None = Field(
        default=None,
        description="The collector's template id, or null when the lines carried none.",
    )
    count: int = Field(description="How many lines in the window folded into this row.")
    first_seen: datetime = Field(description="Oldest line in the cluster, UTC.")
    last_seen: datetime = Field(description="Newest line in the cluster, UTC.")
    worst_level: LogLevel = Field(
        description="Most severe level among the cluster's lines. A level, not a score.",
    )
    levels: dict[str, int] = Field(
        default_factory=dict,
        description="How many lines of each level the cluster holds, keyed by level.",
    )
    hosts: list[str] = Field(default_factory=list, description="Hosts that emitted the cluster.")
    services: list[str] = Field(
        default_factory=list, description="Services that emitted the cluster."
    )
    sample_message: str = Field(description="The newest line in the cluster, verbatim.")
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Parameters of the newest line in the cluster.",
    )


class LogTailOut(BaseModel):
    """Clusters for one window, plus what the tail could and could not cover."""

    start: datetime = Field(description="Window start, inclusive, UTC.")
    end: datetime = Field(description="Window end, exclusive, UTC.")
    clusters: list[LogClusterOut] = Field(default_factory=list)
    lines_seen: int = Field(description="Matching lines folded, before any row limit.")
    clusters_seen: int = Field(description="Distinct clusters in the window, before any limit.")
    clusters_truncated: bool = Field(description="Whether the row limit cut the list.")
    retained_from: datetime | None = Field(
        default=None, description="Oldest instant the tail still holds, or null when empty."
    )
    retained_to: datetime | None = Field(
        default=None, description="Newest instant the tail still holds, or null when empty."
    )
    retained_lines: int = Field(description="Lines held after eviction, across all windows.")
    dropped_lines: int = Field(description="Lines evicted since the process started.")
    caveats: list[str] = Field(
        default_factory=list,
        description="What a reader must know to read the numbers above (R-70).",
    )


class LogLinesOut(BaseModel):
    """The raw lines of one cluster (or one window), oldest first."""

    start: datetime = Field(description="Window start, inclusive, UTC.")
    end: datetime = Field(description="Window end, exclusive, UTC.")
    key: str | None = Field(default=None, description="Cluster the read was narrowed to, if any.")
    lines: list[LogLineOut] = Field(default_factory=list)
    lines_seen: int = Field(description="Matching lines, before the row limit.")
    lines_truncated: bool = Field(description="Whether the newest rows only are shown.")
    retained_from: datetime | None = Field(default=None)
    retained_to: datetime | None = Field(default=None)
    retained_lines: int = Field(description="Lines held after eviction, across all windows.")
    dropped_lines: int = Field(description="Lines evicted since the process started.")
    caveats: list[str] = Field(default_factory=list)
