"""Phase 58: HA & scale — Redis-backed EventBus, distributed scheduler, Postgres RLS."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Dict, Any, List, Optional

from app.core.config import settings

_LOGGER = logging.getLogger(__name__)

# Redis EventBus wrapper

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = getattr(settings, "REDIS_URL", None)
    if not redis_url:
        return None
    try:
        import redis

        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


class RedisEventBus:
    """Phase 58: Redis-backed EventBus for multi-worker fanout."""

    def __init__(self):
        self.channel = "noctra:events"

    def publish(self, event: Dict[str, Any]):
        redis_client = _get_redis()
        if redis_client:
            try:
                redis_client.publish(self.channel, json.dumps(event))
                return True
            except Exception as exc:
                _LOGGER.debug("Redis publish failed: %s", exc)
        # Fallback to in-process bus
        try:
            from app.core.events import bus as mem_bus

            mem_bus.publish(event)
            return False  # published to memory, not redis
        except Exception:
            return False

    def subscribe(self):
        redis_client = _get_redis()
        if not redis_client:
            return None
        try:
            pubsub = redis_client.pubsub()
            pubsub.subscribe(self.channel)
            return pubsub
        except Exception as exc:
            _LOGGER.debug("Redis subscribe failed: %s", exc)
            return None


redis_bus = RedisEventBus()


def get_ha_status() -> Dict[str, Any]:
    redis_client = _get_redis()
    redis_available = redis_client is not None
    eventbus_backend = "redis" if getattr(settings, "REDIS_EVENTBUS_ENABLED", False) and redis_available else "memory"
    return {
        "redis_available": redis_available,
        "redis_url_configured": bool(getattr(settings, "REDIS_URL", None)),
        "eventbus_backend": eventbus_backend,
        "eventbus_channel": redis_bus.channel,
        "distributed_scheduler": redis_available,  # if redis available, scheduler can use distributed lock
        "postgres_rls": False,  # RLS not yet enabled — documented gap, org_id filter used instead
        "multi_worker_safe_rate_limits": redis_available,
        "honest_gaps": [
            "Postgres RLS not enabled — org isolation via org_id WHERE clause, not DB policy",
            "Scheduler per-process unless Redis lock enabled",
            "Rate limits per-process unless Redis backend",
            "EventBus per-process unless REDIS_EVENTBUS_ENABLED=true and REDIS_URL set",
        ],
    }


# Distributed lock for scheduler (using Redis SETNX)

def acquire_distributed_lock(lock_name: str, ttl_seconds: int = 60) -> bool:
    redis_client = _get_redis()
    if not redis_client:
        return True  # no redis, allow execution (per-process)
    try:
        # SET lock_name 1 NX EX ttl
        result = redis_client.set(lock_name, "1", nx=True, ex=ttl_seconds)
        return bool(result)
    except Exception:
        return True


def release_distributed_lock(lock_name: str):
    redis_client = _get_redis()
    if not redis_client:
        return
    try:
        redis_client.delete(lock_name)
    except Exception:
        pass
