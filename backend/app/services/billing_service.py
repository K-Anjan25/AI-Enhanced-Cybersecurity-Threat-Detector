"""Phase 60: Billing + usage metering + quota enforcement."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.billing import OrgUsage, OrgQuota, BillingPlan
from app.models import SecurityAlert, Case, User
from app.core.config import settings


def ensure_default_plans(db: Session):
    existing = {p.name for p in db.query(BillingPlan).all()}
    plans = [
        {"name": "free", "description": "Free tier", "max_alerts": 10000, "max_cases": 1000, "max_users": 5, "price": 0.0, "features": ["alerts", "cases", "basic_threat_intel"]},
        {"name": "pro", "description": "Pro tier", "max_alerts": 100000, "max_cases": 10000, "max_users": 50, "price": 99.0, "features": ["alerts", "cases", "threat_intel", "soar", "api_keys", "sso"]},
        {"name": "enterprise", "description": "Enterprise", "max_alerts": 1000000, "max_cases": 100000, "max_users": 500, "price": 499.0, "features": ["*"]},
    ]
    for plan_data in plans:
        if plan_data["name"] not in existing:
            plan = BillingPlan(
                name=plan_data["name"],
                description=plan_data["description"],
                max_alerts=plan_data["max_alerts"],
                max_cases=plan_data["max_cases"],
                max_users=plan_data["max_users"],
                price_per_month=plan_data["price"],
                features=plan_data["features"],
            )
            db.add(plan)
    db.commit()


def get_org_quota(db: Session, org_id: int) -> OrgQuota:
    quota = db.query(OrgQuota).filter(OrgQuota.org_id == org_id).first()
    if not quota:
        # Create default from free plan
        ensure_default_plans(db)
        free = db.query(BillingPlan).filter(BillingPlan.name == "free").first()
        quota = OrgQuota(
            org_id=org_id,
            max_alerts_per_month=free.max_alerts if free else 10000,
            max_cases_per_month=free.max_cases if free else 1000,
            max_users=free.max_users if free else 5,
        )
        db.add(quota)
        db.commit()
        db.refresh(quota)
    return quota


def get_current_usage(db: Session, org_id: int) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)

    alerts_count = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id, SecurityAlert.created_at >= period_start).count()
    cases_count = db.query(Case).filter(Case.org_id == org_id, Case.created_at >= period_start).count()
    users_count = db.query(User).filter(User.org_id == org_id, User.is_active == True).count()  # noqa: E712

    quota = get_org_quota(db, org_id)

    return {
        "org_id": org_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "alerts_ingested": alerts_count,
        "cases_created": cases_count,
        "users_active": users_count,
        "quota": {
            "max_alerts_per_month": quota.max_alerts_per_month,
            "max_cases_per_month": quota.max_cases_per_month,
            "max_users": quota.max_users,
        },
        "usage_percent": {
            "alerts": (alerts_count / quota.max_alerts_per_month * 100) if quota.max_alerts_per_month else 0,
            "cases": (cases_count / quota.max_cases_per_month * 100) if quota.max_cases_per_month else 0,
            "users": (users_count / quota.max_users * 100) if quota.max_users else 0,
        },
        "over_quota": {
            "alerts": alerts_count >= quota.max_alerts_per_month,
            "cases": cases_count >= quota.max_cases_per_month,
            "users": users_count >= quota.max_users,
        },
    }


def check_quota(db: Session, org_id: int, action: str = "alert") -> bool:
    """Check if org is over quota for action. Returns True if allowed, raises 429 if over."""
    if not getattr(settings, "BILLING_ENABLED", False):
        return True

    usage = get_current_usage(db, org_id)
    if action == "alert" and usage["over_quota"]["alerts"]:
        from fastapi import HTTPException

        raise HTTPException(status_code=429, detail=f"Alert quota exceeded: {usage['alerts_ingested']}/{usage['quota']['max_alerts_per_month']}")
    if action == "case" and usage["over_quota"]["cases"]:
        from fastapi import HTTPException

        raise HTTPException(status_code=429, detail=f"Case quota exceeded")
    if action == "user" and usage["over_quota"]["users"]:
        from fastapi import HTTPException

        raise HTTPException(status_code=429, detail=f"User quota exceeded: {usage['users_active']}/{usage['quota']['max_users']}")
    return True


def record_usage(db: Session, org_id: int, alerts: int = 0, cases: int = 0, api_calls: int = 0):
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)

    usage = db.query(OrgUsage).filter(OrgUsage.org_id == org_id, OrgUsage.period_start == period_start).first()
    if not usage:
        usage = OrgUsage(
            org_id=org_id,
            period_start=period_start,
            period_end=period_end,
            alerts_ingested=0,
            cases_created=0,
            api_calls=0,
        )
        db.add(usage)

    usage.alerts_ingested += alerts
    usage.cases_created += cases
    usage.api_calls += api_calls
    usage.updated_at = now
    db.commit()
    return usage


def list_plans(db: Session) -> List[BillingPlan]:
    ensure_default_plans(db)
    return db.query(BillingPlan).order_by(BillingPlan.price_per_month).all()


def serialize_quota(q: OrgQuota) -> Dict[str, Any]:
    return {
        "org_id": q.org_id,
        "max_alerts_per_month": q.max_alerts_per_month,
        "max_cases_per_month": q.max_cases_per_month,
        "max_api_calls_per_month": q.max_api_calls_per_month,
        "max_storage_mb": q.max_storage_mb,
        "max_users": q.max_users,
        "is_custom": q.is_custom,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }
