from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class Entity(Base):
    """A normalized threat entity observed across alerts: IP, domain, hash,
    email, or file. Entities are tenant-scoped and deduplicated by value."""

    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("org_id", "entity_type", "value", name="uq_entity_scope"),)

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)

    entity_type = Column(String(30), nullable=False)  # ip | domain | hash | email | file
    value = Column(String(500), nullable=False)

    # Aggregate risk across the alerts referencing this entity.
    risk_score = Column(Float, default=0.0, nullable=False)
    occurrences = Column(Integer, default=1, nullable=False)

    # Optional metadata (e.g. TLD for domains, hash algorithm).
    meta = Column(JSON, nullable=True)

    first_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    links_out = relationship(
        "EntityLink",
        foreign_keys="EntityLink.source_entity_id",
        back_populates="source_entity",
    )
    links_in = relationship(
        "EntityLink",
        foreign_keys="EntityLink.target_entity_id",
        back_populates="target_entity",
    )


class EntityLink(Base):
    """A directed relationship between two entities, derived from a shared
    alert (e.g. source_ip -> dst_ip communicates). Drives the attack graph."""

    __tablename__ = "entity_links"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=True, index=True)

    source_entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    target_entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    relation = Column(String(50), nullable=False)  # communicates | derives_from | resolves_to | ...

    # Which alert established this link (optional).
    source_alert_id = Column(Integer, ForeignKey("security_alerts.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    source_entity = relationship("Entity", foreign_keys=[source_entity_id], back_populates="links_out")
    target_entity = relationship("Entity", foreign_keys=[target_entity_id], back_populates="links_in")