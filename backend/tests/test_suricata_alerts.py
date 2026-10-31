"""Suricata alert events reach the alert store, not only the log store.

Covers the two halves of the path: the bridge must emit ``log@1`` records that the
API accepts, and an accepted ``suricata-alert`` record must become an alert row
through the correlator, with a replayed event absorbed rather than counted twice.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.ingest import LogRecordIn
from app.services.alert_store import InMemoryAlertStore
from app.services.detection_engine import DetectionEngine
from app.services.ingest_service import ingest_batch

BRIDGES = Path(__file__).resolve().parents[1] / "app" / "services" / "capture" / "bridges"
sys.path.insert(0, str(BRIDGES))

from suricata_bridge import parse_alert, to_log_v1  # noqa: E402

EVE = {
    "event_type": "alert",
    "timestamp": "2026-10-31T10:00:00.000000+0000",
    "src_ip": "10.0.0.5",
    "src_port": 5555,
    "dest_ip": "203.0.113.9",
    "dest_port": 4444,
    "proto": "TCP",
    "alert": {
        "signature_id": 2100498,
        "signature": "ET MALWARE test beacon",
        "category": "A Network Trojan was detected",
        "severity": 1,
        "action": "allowed",
    },
}


def _accepted(event: dict) -> list:
    body = json.dumps(to_log_v1(parse_alert(event))).encode()
    result, accepted = ingest_batch(body, LogRecordIn, limit=5000, content_type="application/json")
    assert result.rejected == 0, result.errors
    return [r.model_dump() for r in accepted]


def test_alert_record_passes_log_v1_validation() -> None:
    records = _accepted(EVE)
    assert records[0]["service"] == "suricata-alert"
    assert records[0]["parameters"]["signature_id"] == "2100498"
    assert records[0]["parameters"]["dst_port"] == "4444"  # regression: was read from dest_ip


def test_dns_record_is_log_v1() -> None:
    record = to_log_v1(
        {
            "source": "suricata-dns",
            "level": "info",
            "message": "m",
            "host": "",
            "timestamp": "2026-10-31T10:00:01.000000+0000",
            "structured": {"answers": ["a", "b"]},
        }
    )
    result, _ = ingest_batch(
        json.dumps(record).encode(), LogRecordIn, limit=5000, content_type="application/json"
    )
    assert result.rejected == 0
    assert record["parameters"]["answers"] == "a,b"
    assert record["host"] == "unknown"


def test_alert_becomes_alert_row_and_replay_is_absorbed() -> None:
    store = InMemoryAlertStore()
    engine = DetectionEngine(store)
    records = _accepted(EVE)

    assert engine.feed_signatures(records) == 1
    # A replayed event carries the same evidence id, so the correlator absorbs it.
    assert engine.feed_signatures(records) == 0
    rows = store.rows()
    assert len(rows) == 1
    assert rows[0].family == "ids:A Network Trojan was detected"


def test_non_alert_records_are_not_alerts() -> None:
    store = InMemoryAlertStore()
    engine = DetectionEngine(store)
    records = [
        {
            "service": "suricata-dns",
            "timestamp": datetime(2026, 10, 31, tzinfo=UTC),
            "host": "10.0.0.5",
            "parameters": {"query": "example.com"},
        }
    ]
    assert engine.feed_signatures(records) == 0
    assert len(store) == 0
