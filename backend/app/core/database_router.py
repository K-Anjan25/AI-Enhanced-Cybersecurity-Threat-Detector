"""DB routing for future sharding - disabled by default, single DB now."""

from typing import Generator
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.config import settings

# If you enable sharding, set DB_SHARDING_ENABLED=True and provide SHARD_URLS list
# For now, we stay single DB (threatdb) with read replica optional.

def get_write_db() -> Generator[Session, None, None]:
    """Write DB - always primary."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_read_db() -> Generator[Session, None, None]:
    """Read DB - replica if configured, else primary."""
    # If replica URL set, you would create replica engine. For now reuse primary.
    # Future: if settings.DATABASE_REPLICA_URL: use replica SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ShardedSession:
    """Skeleton for org_id based sharding (Citus style). Disabled unless DB_SHARDING_ENABLED."""
    def __init__(self, org_id: int):
        self.org_id = org_id
        self.shard_count = getattr(settings, "DB_SHARD_COUNT", 1)

    def get_shard_id(self) -> int:
        if not getattr(settings, "DB_SHARDING_ENABLED", False):
            return 0
        return self.org_id % self.shard_count

    def get_session(self) -> Session:
        # In sharded mode, you would pick engine based on shard_id
        return SessionLocal()
