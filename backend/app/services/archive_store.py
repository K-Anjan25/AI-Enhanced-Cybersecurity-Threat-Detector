"""Where exported and archived data actually goes.

Two places in this codebase used to claim a destination they never wrote to:
`archive_old_data` logged `s3://archive/...` for a file that was never created,
and `export_to_s3` logged `/tmp/...` with status "success" when S3 was not
configured. Both produced an audit record pointing at nothing — the worst
possible outcome for a compliance feature, because the log is the evidence.

This module gives them one honest destination with three states:

* **S3** when `S3_BUCKET` and credentials are set and `boto3` is installed.
* **Local disk** otherwise — a real file under `ARCHIVE_ROOT` that an operator
  can open, back up, or point a sync job at. Small deployments genuinely do not
  need object storage, so this is a supported mode rather than a degraded one.
* **Failure**, reported as failure. Never a success record for a write that
  did not happen.

Every call returns the same shape, including `stored: bool`. Callers must not
record success without checking it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings

_LOGGER = logging.getLogger(__name__)

# Local fallback lives beside uploads, which is already a writable, mounted
# directory in every deployment.
ARCHIVE_ROOT = Path(__file__).resolve().parents[2] / "archives"


def _s3_configured() -> bool:
    return all(
        getattr(settings, name, None)
        for name in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY")
    )


def describe_destination() -> Dict[str, Any]:
    """Where a write would go right now, for the UI to show before acting."""
    if _s3_configured():
        return {
            "kind": "s3",
            "detail": f"{settings.S3_BUCKET} at {settings.S3_ENDPOINT}",
            "configured": True,
        }
    return {
        "kind": "local",
        "detail": str(ARCHIVE_ROOT),
        "configured": True,
        "note": (
            "No object storage is configured, so archives are written to local "
            "disk on the API host. Set S3_BUCKET to send them off-box."
        ),
    }


def _safe_segment(value: str) -> str:
    """Keep a caller-supplied name from escaping the archive root."""
    cleaned = "".join(c for c in str(value) if c.isalnum() or c in "-_.")
    return cleaned or "unnamed"


def store(
    *,
    org_id: int,
    category: str,
    name: str,
    payload: bytes,
    content_type: str = "application/octet-stream",
) -> Dict[str, Any]:
    """Write `payload` and report exactly where it went, or that it failed.

    Returns ``{stored, destination, path, url, error}``. ``stored`` is the only
    field a caller should branch on: everything else is for the audit record.
    """
    stamp = datetime.now(timezone.utc)
    key = (
        f"{_safe_segment(category)}/{org_id}/"
        f"{stamp.date()}/{_safe_segment(name)}"
    )

    if _s3_configured():
        try:
            import boto3

            client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
            )
            client.put_object(
                Bucket=settings.S3_BUCKET,
                Key=key,
                Body=payload,
                ContentType=content_type,
            )
            return {
                "stored": True,
                "destination": "s3",
                "path": key,
                "url": f"{str(settings.S3_ENDPOINT).rstrip('/')}/{settings.S3_BUCKET}/{key}",
                "error": None,
            }
        except ImportError:
            # Configured but unusable. Falling through to disk would quietly
            # put compliance evidence somewhere the operator is not expecting.
            _LOGGER.error("S3 is configured but boto3 is not installed")
            return {
                "stored": False,
                "destination": "s3",
                "path": None,
                "url": None,
                "error": "S3 is configured but the boto3 package is not installed",
            }
        except Exception as exc:
            _LOGGER.warning("S3 write failed for %s: %s", key, exc)
            return {
                "stored": False,
                "destination": "s3",
                "path": None,
                "url": None,
                "error": f"S3 write failed: {exc}",
            }

    try:
        target = ARCHIVE_ROOT / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return {
            "stored": True,
            "destination": "local",
            "path": str(target),
            "url": None,
            "error": None,
        }
    except Exception as exc:
        _LOGGER.warning("Local archive write failed for %s: %s", key, exc)
        return {
            "stored": False,
            "destination": "local",
            "path": None,
            "url": None,
            "error": f"Could not write to {ARCHIVE_ROOT}: {exc}",
        }
