"""ORM models for the PostgreSQL schema in architecture.md §6.

Two consequences of declarative partitioning shape this file, and both are the
kind of thing that fails only against a real server.

**A partitioned table's primary key must include the partition key.** Postgres
enforces uniqueness per partition, so a key that does not contain the partition
column cannot be enforced globally. `alerts` is therefore keyed ``(id,
created_at)`` and `ingest_stats` ``(id, window_start)`` rather than by ``id``
alone. Nothing downstream should rely on `id` being unique on its own for those
two tables.

**Partitioned tables carry no default partition here.** A row whose timestamp
falls outside every existing partition is rejected rather than filed somewhere
unnoticed, because a silently accumulating default partition defeats the retention
model that dropping partitions provides (NFR-05, GDPR erasure). Partitions are
created ahead of time by :mod:`app.db.partitions`.

`audit_log` deliberately has no update or delete path, per R-31. That is asserted
in the tests rather than left as a comment.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Tables partitioned monthly by time. R-34 restricts queries against these.
PARTITIONED_TABLES: frozenset[str] = frozenset({"alerts", "ingest_stats"})


class Base(DeclarativeBase):
    """Declarative base for every model."""


class UserRole(enum.StrEnum):
    """Role names, matching architecture.md §6."""

    viewer = "viewer"
    analyst = "analyst"
    responder = "responder"
    admin = "admin"


class EntityKind(enum.StrEnum):
    """What an entity is."""

    host = "host"
    ip = "ip"
    user = "user"
    service = "service"


class AlertStatus(enum.StrEnum):
    """Alert lifecycle."""

    open = "open"
    acknowledged = "acknowledged"
    closed = "closed"


class Verdict(enum.StrEnum):
    """Analyst verdict. Absent means not yet triaged."""

    true_positive = "true_positive"
    false_positive = "false_positive"
    benign = "benign"


class ModelStatus(enum.StrEnum):
    """Model lifecycle, mirroring the registry in ml-service (R-68)."""

    staging = "staging"
    active = "active"
    retired = "retired"


class ModelKind(enum.StrEnum):
    """Which model this is, per FR-30."""

    flow = "flow"
    log = "log"


class User(Base):
    """An authenticated principal."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    argon2_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_type=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiKey(Base):
    """A scoped API key. Only a hash is stored (T-313)."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False, default=list)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Entity(Base):
    """A host, address, user or service that alerts attach to."""

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[EntityKind] = mapped_column(
        Enum(EntityKind, name="entity_kind", create_type=True), nullable=False
    )
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meta: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("uq_entities_kind_value", "kind", "value", unique=True),
        Index("ix_entities_last_seen", "last_seen"),
    )


class Alert(Base):
    """A ranked detection. Partitioned monthly on ``created_at``."""

    __tablename__ = "alerts"

    # The partition key is part of the primary key: see the module docstring.
    # Both columns must be declared as key columns explicitly -- omitting either
    # leaves the mapper with no primary key at all, and `id` alone cannot be
    # enforced globally across partitions.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        primary_key=True,
    )
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    family: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    model_flow_id: Mapped[str | None] = mapped_column(String(200))
    model_log_id: Mapped[str | None] = mapped_column(String(200))
    window_ref: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    explanation: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status", create_type=True),
        nullable=False,
        default=AlertStatus.open,
    )
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verdict: Mapped[Verdict | None] = mapped_column(Enum(Verdict, name="verdict", create_type=True))
    verdict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verdict_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = ({"postgresql_partition_by": "RANGE (created_at)"},)


class ModelRecord(Base):
    """A registered model. Named to avoid shadowing the ``models`` package."""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[ModelKind] = mapped_column(
        Enum(ModelKind, name="model_kind", create_type=True), nullable=False
    )
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    training_manifest: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    status: Mapped[ModelStatus] = mapped_column(
        Enum(ModelStatus, name="model_status", create_type=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("uq_models_name_version", "name", "version", unique=True),)


class ModelVersionHistory(Base):
    """Promotion and rollback history."""

    __tablename__ = "model_versions_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), nullable=False)
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    promoted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Append-only record of every mutating route (R-31, T-312).

    There is deliberately no relationship back to the actor and no update path.
    R-31 requires that the ORM expose no way to mutate or delete these rows, and
    the test suite asserts that rather than trusting the absence of a method.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(120), nullable=False)
    detail: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    ip: Mapped[str | None] = mapped_column(INET)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_audit_log_at", "at"),)


class Threshold(Base):
    """A detection threshold per tenant, family and band (T-207)."""

    __tablename__ = "thresholds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(80), nullable=False)
    family: Mapped[str] = mapped_column(String(80), nullable=False)
    band: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("uq_thresholds_tenant_family_band", "tenant_id", "family", "band", unique=True),
    )


class IngestStat(Base):
    """Ingest accounting. Partitioned monthly on ``window_start``."""

    __tablename__ = "ingest_stats"

    # Partition key in the primary key, for the same reason as Alert.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, primary_key=True
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_reasons: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = ({"postgresql_partition_by": "RANGE (window_start)"},)


#: Every model, for migration autogeneration and for tests that walk the schema.
ALL_TABLES: tuple[str, ...] = (
    "users",
    "api_keys",
    "entities",
    "alerts",
    "models",
    "model_versions_history",
    "audit_log",
    "thresholds",
    "ingest_stats",
)

#: The column each partitioned table is ranged on.
PARTITION_KEYS: dict[str, str] = {"alerts": "created_at", "ingest_stats": "window_start"}

__all__ = [
    "ALL_TABLES",
    "PARTITIONED_TABLES",
    "PARTITION_KEYS",
    "Alert",
    "AlertStatus",
    "ApiKey",
    "AuditLog",
    "Base",
    "Entity",
    "EntityKind",
    "IngestStat",
    "ModelKind",
    "ModelRecord",
    "ModelStatus",
    "ModelVersionHistory",
    "Threshold",
    "User",
    "UserRole",
    "Verdict",
    "Boolean",
]
