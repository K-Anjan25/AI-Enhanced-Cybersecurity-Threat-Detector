"""Phase 60: Billing + usage metering + quota enforcement."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Float, JSON
from app.core.database import Base


class OrgUsage(Base):
    __tablename__ = "org_usages"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True)

    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    alerts_ingested = Column(Integer, default=0, nullable=False)
    cases_created = Column(Integer, default=0, nullable=False)
    api_calls = Column(Integer, default=0, nullable=False)
    storage_mb = Column(Float, default=0.0, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class OrgQuota(Base):
    __tablename__ = "org_quotas"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    max_alerts_per_month = Column(Integer, default=10000, nullable=False)
    max_cases_per_month = Column(Integer, default=1000, nullable=False)
    max_api_calls_per_month = Column(Integer, default=100000, nullable=False)
    max_storage_mb = Column(Float, default=10240.0, nullable=False)  # 10GB
    max_users = Column(Integer, default=100, nullable=False)

    is_custom = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class BillingPlan(Base):
    __tablename__ = "billing_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)  # free, pro, enterprise
    description = Column(String(500), nullable=True)

    max_alerts = Column(Integer, default=10000)
    max_cases = Column(Integer, default=1000)
    max_users = Column(Integer, default=10)
    price_per_month = Column(Float, default=0.0)

    features = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
