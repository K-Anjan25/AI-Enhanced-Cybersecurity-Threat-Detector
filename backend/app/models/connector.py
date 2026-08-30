"""Connector sources — configuration and sync state for real telemetry ingest.

Before this table existed, the connectors panel was a hardcoded list that
claimed to be "connected" with invented asset counts, and "Sync" returned
success without contacting anything. A connector is only *connected* now if a
source row exists, is enabled, and its last sync actually succeeded — every
number shown is derived from rows this deployment really ingested.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.core.database import Base


class ConnectorSource(Base):
    """Tenant-scoped configuration + last-sync state for one connector.

    Two ingest modes are supported, both real:
      - ``poll``  — NOCTRA fetches ``endpoint`` on demand (and could on a timer).
      - ``push``  — the source POSTs events to /ingest/connector/{id} using
                    ``ingest_token`` as a shared secret.

    ``auth_token`` (outbound credential) is never returned by any endpoint.
    """

    __tablename__ = "connector_sources"
    __table_args__ = (
        UniqueConstraint("org_id", "connector_id", name="uq_connector_source_org"),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)

    connector_id = Column(String(40), nullable=False, index=True)  # okta | sentinel | ...
    name = Column(String(120), nullable=False)
    category = Column(String(60), nullable=False)

    mode = Column(String(10), nullable=False, default="push")  # poll | push
    endpoint = Column(Text, nullable=True)  # poll mode: where to fetch events
    auth_header = Column(String(80), nullable=True)  # poll mode: e.g. "Authorization"
    auth_token = Column(Text, nullable=True)  # poll mode: outbound credential (never returned)
    ingest_token = Column(Text, nullable=True)  # push mode: shared secret for the sender

    enabled = Column(Boolean, default=True, nullable=False)

    # Real sync state — all null until a sync actually runs.
    last_sync_at = Column(DateTime, nullable=True)
    last_status = Column(String(20), nullable=True)  # ok | error
    last_error = Column(Text, nullable=True)
    last_duration_ms = Column(Integer, nullable=True)
    last_count = Column(Integer, nullable=True)
    events_ingested = Column(Integer, default=0, nullable=False)

    # Phase 42: incremental sync — cursor/pagination state for real APIs (GitHub, Slack, etc)
    # IANA zone (e.g. "America/New_York") for timestamps this source sends
    # without an offset. Naive timestamps are otherwise read as UTC, which is
    # right for every provider wired up so far but silently wrong for one
    # emitting local time — and unlike a bad field mapping, that produces a
    # plausible number rather than a NULL, so nothing downstream can detect it.
    # There is no way to infer this from the payload, so it must be declared.
    event_time_zone = Column(String(64), nullable=True)

    last_cursor = Column(Text, nullable=True)  # opaque cursor for next page / incremental sync
    sync_state = Column(Text, nullable=True)  # JSON blob for provider-specific state (etag, since, etc)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
