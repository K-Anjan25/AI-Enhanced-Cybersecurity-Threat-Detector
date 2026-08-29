"""Phase 47: API keys + service accounts + per-org rate limiting.

- API key format sk_{prefix}_{secret}, prefix 8 chars alphanumeric, secret 32 urlsafe.
- Hash stored with bcrypt (passlib).
- Verify: parse prefix, lookup, bcrypt verify.
- Service accounts: create User with is_service_account=True, then ServiceAccount wrapper.
- Rate limiting: per-org token bucket, Redis optional, in-memory fallback.
  Configurable via ORG_RATE_LIMIT_RPS (default 100 req/s burst 200) and ORG_RATE_LIMIT_ENABLED.

Multi-tenant isolation: every query filters by org_id; middleware dependency checks.

"""
from __future__ import annotations

import hashlib
import secrets
import string
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict, Any
from collections import defaultdict, deque

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import User, Org
from app.models.apikey import ApiKey, ServiceAccount
from app.core.security import get_password_hash, verify_password
from app.core.config import settings

# ---------------------------------------------------------------------------
# In-memory rate limiting fallback (per-org)
# ---------------------------------------------------------------------------

# org_id -> deque of timestamps (float)
_org_buckets: Dict[int, deque] = defaultdict(deque)
_org_last_cleanup: Dict[int, float] = {}

# Optional Redis client
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    # Try to connect if REDIS_URL set
    redis_url = getattr(settings, "REDIS_URL", None)
    if not redis_url:
        return None
    try:
        import redis  # type: ignore

        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def check_org_rate_limit(org_id: int) -> None:
    """Enforce per-org rate limit. Raises 429 if exceeded.

    Honors settings ORG_RATE_LIMIT_ENABLED (default True), ORG_RATE_LIMIT_RPS (default 100),
    ORG_RATE_LIMIT_BURST (default 200). If Redis available, uses INCR with TTL sliding window.
    Otherwise in-memory deque window 1 second for RPS + burst check.

    """
    enabled = getattr(settings, "ORG_RATE_LIMIT_ENABLED", True)
    if not enabled:
        return

    rps = getattr(settings, "ORG_RATE_LIMIT_RPS", 100)
    burst = getattr(settings, "ORG_RATE_LIMIT_BURST", 200)

    redis_client = _get_redis()
    now = time.time()

    if redis_client:
        try:
            # Simple fixed window: per-second counter + burst via second key?
            # We implement 2 checks: 1s window RPS, 60s window burst*60?
            # Simpler: use sorted set? Use INCR for 1s window.
            # Use key org:rl:{org_id}:{second}
            sec = int(now)
            key_sec = f"org:rl:{org_id}:{sec}"
            count = redis_client.incr(key_sec)
            if count == 1:
                redis_client.expire(key_sec, 2)
            if count > burst:  # burst as per-second hard cap
                raise HTTPException(
                    status_code=429,
                    detail=f"Org rate limit exceeded: {count} > {burst} req/s",
                    headers={"Retry-After": "1"},
                )
            # Also check rolling 60s approx: sum last 60 keys? For simplicity skip, or check RPS * 60
            # Implement longer window key
            key_min = f"org:rl:min:{org_id}:{sec // 60}"
            count_min = redis_client.incr(key_min)
            if count_min == 1:
                redis_client.expire(key_min, 70)
            if count_min > rps * 60:
                raise HTTPException(
                    status_code=429,
                    detail=f"Org rate limit exceeded (per-minute): {count_min} > {rps*60}",
                    headers={"Retry-After": "60"},
                )
            return
        except HTTPException:
            raise
        except Exception:
            # fallback to memory
            pass

    # In-memory fallback
    dq = _org_buckets[org_id]
    # cleanup older than 60s for minute check
    cutoff_60 = now - 60
    while dq and dq[0] < cutoff_60:
        dq.popleft()
    # count last second
    cutoff_1 = now - 1
    count_1s = sum(1 for t in dq if t >= cutoff_1)
    if count_1s >= burst:
        raise HTTPException(
            status_code=429,
            detail=f"Org rate limit exceeded: {count_1s} >= {burst} req/s (in-memory)",
            headers={"Retry-After": "1"},
        )
    if len(dq) >= rps * 60:
        raise HTTPException(
            status_code=429,
            detail=f"Org rate limit exceeded per-minute: {len(dq)} >= {rps*60}",
            headers={"Retry-After": "60"},
        )
    dq.append(now)


# ---------------------------------------------------------------------------
# API Key helpers
# ---------------------------------------------------------------------------

_ALPHANUM = string.ascii_letters + string.digits


def _gen_prefix(length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHANUM) for _ in range(length))


def _gen_secret(length: int = 32) -> str:
    # urlsafe, 32 chars ~ 192 bits
    return secrets.token_urlsafe(24)[:length]  # ensure length


def _hash_secret(secret: str) -> str:
    # bcrypt via passlib
    return get_password_hash(secret)


def _verify_secret(plain: str, hashed: str) -> bool:
    try:
        return verify_password(plain, hashed)
    except Exception:
        return False


def parse_api_key(raw: str) -> Tuple[str, str] | None:
    """Parse sk_{prefix}_{secret} -> (prefix, secret). Returns None if invalid format."""
    if not raw or not raw.startswith("sk_"):
        return None
    # format sk_{prefix}_{secret}
    try:
        # remove sk_
        remainder = raw[3:]
        # prefix is first 8 chars, then '_' then secret
        if "_" not in remainder:
            return None
        prefix, secret = remainder.split("_", 1)
        if len(prefix) < 6 or len(secret) < 16:
            return None
        return prefix, secret
    except Exception:
        return None


def create_api_key(
    db: Session,
    org_id: int,
    name: str,
    scopes: str = "alerts:read",
    created_by_user_id: int | None = None,
    service_account_id: int | None = None,
    expires_days: int | None = None,
) -> Tuple[ApiKey, str]:
    """Create new API key, returns (record, raw_key). Raw key shown once."""
    # ensure unique prefix, retry up to 5
    prefix = None
    for _ in range(5):
        cand = _gen_prefix(8)
        existing = db.query(ApiKey).filter(ApiKey.prefix == cand).first()
        if not existing:
            prefix = cand
            break
    if prefix is None:
        raise ValueError("Failed to generate unique prefix")

    secret = _gen_secret(32)
    hashed = _hash_secret(secret)
    raw_key = f"sk_{prefix}_{secret}"
    last4 = secret[-4:]

    expires_at = None
    if expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    record = ApiKey(
        org_id=org_id,
        name=name,
        prefix=prefix,
        hashed_secret=hashed,
        last4=last4,
        created_by_user_id=created_by_user_id,
        scopes=scopes,
        service_account_id=service_account_id,
        is_active=True,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, raw_key


def verify_api_key(db: Session, raw_key: str) -> Optional[ApiKey]:
    """Verify raw API key, returns ApiKey record if valid and active, else None."""
    parsed = parse_api_key(raw_key)
    if not parsed:
        return None
    prefix, secret = parsed
    record = db.query(ApiKey).filter(ApiKey.prefix == prefix, ApiKey.is_active == True).first()  # noqa: E712
    if not record:
        return None
    if record.expires_at and record.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        # expired (naive comparison handling)
        # try aware
        try:
            if record.expires_at.tzinfo is None:
                exp = record.expires_at.replace(tzinfo=timezone.utc)
            else:
                exp = record.expires_at
            if exp < datetime.now(timezone.utc):
                return None
        except Exception:
            pass
    if not _verify_secret(secret, record.hashed_secret):
        return None
    # update last_used
    try:
        record.last_used_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
    return record


def list_api_keys(db: Session, org_id: int) -> List[ApiKey]:
    return (
        db.query(ApiKey)
        .filter(ApiKey.org_id == org_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


def revoke_api_key(db: Session, org_id: int, key_id: int) -> ApiKey:
    rec = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.org_id == org_id).first()
    if not rec:
        raise ValueError("API key not found")
    rec.is_active = False
    rec.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)
    return rec


def serialize_api_key(k: ApiKey) -> dict:
    return {
        "id": k.id,
        "org_id": k.org_id,
        "name": k.name,
        "prefix": k.prefix,
        "last4": k.last4,
        "scopes": k.scopes,
        "is_active": k.is_active,
        "created_by_user_id": k.created_by_user_id,
        "service_account_id": k.service_account_id,
        "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
    }


# ---------------------------------------------------------------------------
# Service accounts
# ---------------------------------------------------------------------------

def create_service_account(
    db: Session,
    org_id: int,
    name: str,
    description: str | None = None,
    role: str = "service",
    created_by_user_id: int | None = None,
) -> Tuple[ServiceAccount, User]:
    """Create a service account: creates User with is_service_account=True + ServiceAccount record."""
    # ensure unique username
    base_username = f"svc_{name.lower().replace(' ', '_')}_{secrets.token_hex(2)}"
    # truncate to 100 chars (User.username limit)
    base_username = base_username[:90]
    # ensure not exists
    for _ in range(3):
        if not db.query(User).filter(User.username == base_username).first():
            break
        base_username = f"svc_{name.lower().replace(' ', '_')}_{secrets.token_hex(3)}"[:90]
    else:
        raise ValueError("Failed to generate unique service account username")

    # create user row
    user = User(
        org_id=org_id,
        username=base_username,
        password=get_password_hash(secrets.token_urlsafe(32)),  # random, not used for login
        email=f"{base_username}@service.local",
        role=role,
        is_active=True,
        is_service_account=True,
    )
    db.add(user)
    db.flush()  # get user.id

    sa = ServiceAccount(
        org_id=org_id,
        user_id=user.id,
        name=name,
        description=description,
        created_by_user_id=created_by_user_id,
        is_active=True,
    )
    db.add(sa)
    db.commit()
    db.refresh(sa)
    db.refresh(user)
    return sa, user


def list_service_accounts(db: Session, org_id: int) -> List[ServiceAccount]:
    return (
        db.query(ServiceAccount)
        .filter(ServiceAccount.org_id == org_id)
        .order_by(ServiceAccount.created_at.desc())
        .all()
    )


def get_service_account(db: Session, org_id: int, sa_id: int) -> Optional[ServiceAccount]:
    return (
        db.query(ServiceAccount)
        .filter(ServiceAccount.id == sa_id, ServiceAccount.org_id == org_id)
        .first()
    )


def revoke_service_account(db: Session, org_id: int, sa_id: int) -> ServiceAccount:
    sa = get_service_account(db, org_id, sa_id)
    if not sa:
        raise ValueError("Service account not found")
    sa.is_active = False
    # also deactivate user
    user = db.query(User).filter(User.id == sa.user_id).first()
    if user:
        user.is_active = False
    # revoke all api keys for this SA
    db.query(ApiKey).filter(ApiKey.service_account_id == sa_id).update(
        {"is_active": False, "revoked_at": datetime.now(timezone.utc)}
    )
    db.commit()
    db.refresh(sa)
    return sa


def serialize_service_account(sa: ServiceAccount) -> dict:
    return {
        "id": sa.id,
        "org_id": sa.org_id,
        "user_id": sa.user_id,
        "name": sa.name,
        "description": sa.description,
        "is_active": sa.is_active,
        "created_by_user_id": sa.created_by_user_id,
        "created_at": sa.created_at.isoformat() if sa.created_at else None,
        "username": sa.user.username if sa.user else None,
        "role": sa.user.role if sa.user else None,
    }
