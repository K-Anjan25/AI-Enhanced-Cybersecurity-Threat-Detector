"""Phase 59: PWA + push notifications + offline queue."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings

_LOGGER = logging.getLogger(__name__)

# In-memory push subscription store (per-org) — in production, use DB table
_push_subscriptions: Dict[int, List[Dict[str, Any]]] = {}


def subscribe_push(db: Session, org_id: int, user_id: int, subscription: Dict[str, Any]) -> Dict[str, Any]:
    """Store push subscription (Web Push API)."""
    # subscription contains endpoint, keys
    if org_id not in _push_subscriptions:
        _push_subscriptions[org_id] = []
    # Deduplicate by endpoint
    endpoint = subscription.get("endpoint")
    existing = [s for s in _push_subscriptions[org_id] if s.get("endpoint") == endpoint]
    if not existing:
        _push_subscriptions[org_id].append(
            {
                "user_id": user_id,
                "endpoint": endpoint,
                "keys": subscription.get("keys", {}),
                "subscribed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return {"status": "subscribed", "endpoint": endpoint}


def list_push_subscriptions(org_id: int) -> List[Dict[str, Any]]:
    return _push_subscriptions.get(org_id, [])


def send_push_notification(org_id: int, title: str, body: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
    """Send push to all subscriptions in org — honest: if no VAPID keys, logs only."""
    subs = _push_subscriptions.get(org_id, [])
    if not subs:
        return {"sent": 0, "reason": "No subscriptions"}

    # Try webpush if pywebpush available and VAPID configured
    try:
        from pywebpush import webpush

        vapid_private = getattr(settings, "VAPID_PRIVATE_KEY", None)
        vapid_public = getattr(settings, "VAPID_PUBLIC_KEY", None)
        if not vapid_private or not vapid_public:
            _LOGGER.info("Push notification (no VAPID): %s - %s to %d subs", title, body, len(subs))
            return {"sent": 0, "reason": "VAPID not configured, logged only", "would_send": len(subs)}

        sent = 0
        for sub in subs:
            try:
                webpush(
                    subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
                    data=f"{title}: {body}",
                    vapid_private_key=vapid_private,
                    vapid_claims={"sub": "mailto:admin@noctra.ai"},
                )
                sent += 1
            except Exception as exc:
                _LOGGER.debug("Push failed for %s: %s", sub["endpoint"][:30], exc)
        return {"sent": sent, "total": len(subs)}
    except ImportError:
        _LOGGER.info("Push notification (pywebpush not installed): %s - %s to %d subs", title, body, len(subs))
        return {"sent": 0, "reason": "pywebpush not installed", "would_send": len(subs)}
    except Exception as exc:
        _LOGGER.warning("Push send failed: %s", exc)
        return {"sent": 0, "error": str(exc)[:200]}


def get_pwa_manifest() -> Dict[str, Any]:
    return {
        "name": "NOCTRA - Threat Intelligence",
        "short_name": "NOCTRA",
        "description": "Threat intelligence, always on.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#070b0f",
        "theme_color": "#a6ff3f",
        "icons": [
            {"src": "/icons/icon-192x192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icons/icon-512x512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }


def get_offline_queue_status(org_id: int) -> Dict[str, Any]:
    # In real PWA, offline queue is client-side IndexedDB; server reports sync status
    return {
        "org_id": org_id,
        "offline_capable": True,
        "queue_backend": "IndexedDB (client)",
        "sync_endpoint": "/api/v1/sync/offline-queue",
        "honest_note": "Offline queue is client-side; server only provides sync endpoint and reports status",
    }
