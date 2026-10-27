"""The trained flow model's path into alerts (2b backend half), and capture-to-ingest (2c).

Covered here:

- ``_flow_record`` reads both the ``flow@1`` shape ingest stores and the legacy shape.
  Before this, every ingested flow was a zero-byte TCP flow at time zero.
- A window the model scores at or above the threshold raises a ``flow_anomaly`` alert
  with the model id. A window below it raises nothing.
- A failed scorer raises nothing and is counted. It never records a zero score.
- The per-cycle window cap resets each cycle; it is not a lifetime cap.
- ``MlWindowScorer`` returns ``None`` for an unreachable service, a 503 and a malformed
  reply, and a score for a good reply from a real local HTTP server.
- Each capture converter produces records that the real ``FlowRecordIn`` accepts, and
  the ingest endpoint takes them. Real capture still needs the user's Docker run.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.schemas.ingest import FlowRecordIn
from app.services.alert_store import InMemoryAlertStore
from app.services.detection_engine import DetectionEngine
from app.services.ml_window_scorer import MlWindowScorer, _parse
from app.services.rule_detector import (
    MlWindowResult,
    RuleDetector,
    _flow_record,
)
from fastapi.testclient import TestClient

BRIDGES = Path(__file__).resolve().parents[1] / "app" / "services" / "capture" / "bridges"
CAPTURE_SERVICE = (
    Path(__file__).resolve().parents[1] / "app" / "services" / "capture" / "capture_service.py"
)
SECRET = "i" * 48


# ── helpers ─────────────────────────────────────────────────────────────────────


def flow_v1(**overrides: Any) -> dict[str, Any]:
    """A flow@1 dict as ingest stores it (``model_dump`` output: datetime, IPv4 as text)."""
    record: dict[str, Any] = {
        "schema_version": "flow@1",
        "timestamp": datetime(2026, 10, 17, 10, 0, 0, tzinfo=UTC),
        "src_ip": "10.0.0.5",
        "dst_ip": "8.8.8.8",
        "src_port": 51000,
        "dst_port": 443,
        "protocol": "tcp",
        "direction": "outbound",
        "service": "ssl",
        "state": "ESTABLISHED",
        "packets": 11,
        "src_packets": 5,
        "dst_packets": 6,
        "src_bytes": 100,
        "dst_bytes": 900,
        "duration": 1.2,
        "label": None,
    }
    record.update(overrides)
    return record


def window(src: str = "10.0.0.5", n: int = 3) -> list[dict[str, Any]]:
    return [
        flow_v1(src_ip=src, timestamp=datetime(2026, 10, 17, 10, 0, i, tzinfo=UTC))
        for i in range(n)
    ]


class FakeScorer:
    """A scorer that returns a fixed result and records what it was given."""

    def __init__(self, result: MlWindowResult | None) -> None:
        """Hold the result to return for every window."""
        self.result = result
        self.calls: list[list[dict[str, object]]] = []

    def score(self, flows: list[dict[str, object]]) -> MlWindowResult | None:
        self.calls.append(flows)
        return self.result


def model_hit(score: float = 0.97) -> MlWindowResult:
    return MlWindowResult(
        score=score,
        model_id="flownet-v0.1.0",
        reasons=("Inter-arrival times are unusually regular",),
        partial_evidence=True,
    )


def load_bridge(name: str) -> Any:
    """Import a bridge file by path, as its container runs it."""
    spec = importlib.util.spec_from_file_location(f"bridge_{name}", BRIDGES / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_capture_service() -> Any:
    spec = importlib.util.spec_from_file_location("capture_service_under_test", CAPTURE_SERVICE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


# ── _flow_record: both shapes ───────────────────────────────────────────────────


def test_flow_record_reads_flow_v1_shape() -> None:
    record = _flow_record(flow_v1())
    assert record.proto == "tcp"
    assert record.orig_bytes == 100
    assert record.resp_bytes == 900
    assert record.ts == pytest.approx(datetime(2026, 10, 17, 10, 0, 0, tzinfo=UTC).timestamp())


def test_flow_record_still_reads_legacy_shape() -> None:
    record = _flow_record(
        {
            "ts": 1700000000.5,
            "src_ip": "10.0.0.5",
            "dst_ip": "8.8.8.8",
            "src_port": 1,
            "dst_port": 2,
            "proto": "udp",
            "orig_bytes": 7,
            "resp_bytes": 9,
            "duration": 0.5,
        }
    )
    assert (record.proto, record.orig_bytes, record.resp_bytes, record.ts) == (
        "udp",
        7,
        9,
        1700000000.5,
    )


# ── RuleDetector with the trained model ─────────────────────────────────────────


def test_no_scorer_means_no_flow_anomaly() -> None:
    detector = RuleDetector(InMemoryAlertStore())
    alerts = detector.process_flows(window())
    assert all(a["family"] != "flow_anomaly" for a in alerts)
    assert detector.stats["ml_windows_scored"] == 0


def test_window_at_threshold_raises_flow_anomaly_with_model_id() -> None:
    scorer = FakeScorer(model_hit(0.97))
    detector = RuleDetector(InMemoryAlertStore(), ml_scorer=scorer, ml_threshold=0.5)
    alerts = detector.process_flows(window())
    anomalies = [a for a in alerts if a["family"] == "flow_anomaly"]
    assert len(anomalies) == 1
    assert anomalies[0]["score"] == pytest.approx(0.97)
    assert len(scorer.calls) == 1
    # The scorer gets the ingested dicts, not a reshaped copy.
    assert scorer.calls[0][0]["schema_version"] == "flow@1"


def test_flow_anomaly_reasons_say_only_flow_evidence_is_used() -> None:
    detector = RuleDetector(InMemoryAlertStore(), ml_scorer=FakeScorer(model_hit()))
    alerts = detector.process_flows(window())
    reasons = next(a for a in alerts if a["family"] == "flow_anomaly")["explanation"]
    assert reasons[0] == "Flow evidence only: the log model is not serving"
    assert "Inter-arrival times are unusually regular" in reasons


def test_window_below_threshold_raises_nothing() -> None:
    detector = RuleDetector(
        InMemoryAlertStore(), ml_scorer=FakeScorer(model_hit(0.2)), ml_threshold=0.5
    )
    alerts = detector.process_flows(window())
    assert all(a["family"] != "flow_anomaly" for a in alerts)


def test_failed_scorer_raises_nothing_and_is_counted() -> None:
    detector = RuleDetector(InMemoryAlertStore(), ml_scorer=FakeScorer(None))
    alerts = detector.process_flows(window())
    assert all(a["family"] != "flow_anomaly" for a in alerts)
    stats = detector.stats
    assert stats["ml_errors"] == 1
    assert stats["ml_windows_scored"] == 1


def test_single_flow_window_is_not_scored() -> None:
    scorer = FakeScorer(model_hit())
    detector = RuleDetector(InMemoryAlertStore(), ml_scorer=scorer)
    detector.process_flows(window(n=1))
    assert scorer.calls == []


def test_window_cap_is_per_cycle_not_lifetime() -> None:
    scorer = FakeScorer(None)
    detector = RuleDetector(InMemoryAlertStore(), ml_scorer=scorer, ml_max_windows=1)
    many = window("10.0.0.5") + window("10.0.0.6") + window("10.0.0.7")
    detector.process_flows(many)
    assert len(scorer.calls) == 1
    detector.process_flows(window("10.0.0.8") + window("10.0.0.9"))
    assert len(scorer.calls) == 2, "the cap must reset in the next cycle"


# ── DetectionEngine: the path the ingest endpoint uses ──────────────────────────


def test_engine_cycle_scores_fed_flows() -> None:
    scorer = FakeScorer(model_hit())
    engine = DetectionEngine(InMemoryAlertStore(), ml_scorer=scorer)
    engine.feed(window())
    engine._run_cycle()
    assert len(scorer.calls) == 1
    assert engine.stats["ml_windows_scored"] == 1


# ── MlWindowScorer ──────────────────────────────────────────────────────────────


def test_scorer_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError):
        MlWindowScorer("file:///etc/passwd")


def test_scorer_returns_none_when_service_is_unreachable() -> None:
    scorer = MlWindowScorer("http://127.0.0.1:9", timeout=0.5)
    assert scorer.score(window()) is None


def test_scorer_returns_none_for_empty_window() -> None:
    assert MlWindowScorer("http://127.0.0.1:9").score([]) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"score": 1.5, "model_id": "m"},
        {"score": -0.1, "model_id": "m"},
        {"score": True, "model_id": "m"},
        {"score": 0.9},
        {"model_id": "m"},
        ["not", "a", "dict"],
    ],
)
def test_parse_refuses_malformed_replies(payload: object) -> None:
    assert _parse(payload) is None


def test_parse_accepts_a_good_reply() -> None:
    result = _parse({"score": 0.8, "model_id": "flownet-v0.1.0", "reasons": ["a", "b"]})
    assert result is not None
    assert result.score == 0.8
    assert result.model_id == "flownet-v0.1.0"
    assert result.reasons == ("a", "b")


class _Handler(BaseHTTPRequestHandler):
    reply: tuple[int, bytes] = (200, b"{}")
    received: list[bytes] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        length = int(self.headers.get("Content-Length", 0))
        type(self).received.append(self.rfile.read(length))
        status, body = type(self).reply
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture
def ml_http() -> Any:
    _Handler.received = []
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, _Handler
    finally:
        server.shutdown()
        server.server_close()


def test_scorer_round_trip_against_a_live_endpoint(ml_http: Any) -> None:
    server, handler = ml_http
    handler.reply = (
        200,
        json.dumps({"score": 0.91, "model_id": "flownet-v0.1.0", "reasons": ["r"]}).encode(),
    )
    scorer = MlWindowScorer(f"http://127.0.0.1:{server.server_port}", timeout=5)
    result = scorer.score(window())
    assert result is not None
    assert result.score == pytest.approx(0.91)
    sent = json.loads(handler.received[0])
    assert len(sent["flows"]) == 3
    assert sent["flows"][0]["timestamp"].startswith("2026-10-17T10:00:00")


def test_scorer_returns_none_on_503(ml_http: Any) -> None:
    server, handler = ml_http
    handler.reply = (503, b'{"detail":"no checkpoint loaded"}')
    scorer = MlWindowScorer(f"http://127.0.0.1:{server.server_port}", timeout=5)
    assert scorer.score(window()) is None


# ── capture converters against the real ingest contract ─────────────────────────


def legacy_flow(**overrides: Any) -> dict[str, Any]:
    """An aggregated capture flow in the shape the capture aggregator produces."""
    record: dict[str, Any] = {
        "ts": 1_792_000_000.5,
        "src_ip": "10.0.0.5",
        "dst_ip": "8.8.8.8",
        "src_port": 51000,
        "dst_port": 443,
        "proto": "tcp",
        "service": "ssl",
        "orig_bytes": 100,
        "resp_bytes": 900,
        "orig_pkts": 5,
        "resp_pkts": 6,
        "duration": 1.2,
        "conn_state": "SF",
        "source": "tshark",
        "last_seen": 1_792_000_001.7,
    }
    record.update(overrides)
    return record


def test_capture_service_converter_output_is_valid_flow_v1() -> None:
    module = load_capture_service()
    out = module.to_flow_v1(legacy_flow())
    assert out is not None
    FlowRecordIn.model_validate(out)
    assert out["direction"] == "outbound"
    assert out["packets"] == 11


def test_capture_service_converter_drops_non_ipv4_and_unknown_protocols() -> None:
    module = load_capture_service()
    assert module.to_flow_v1(legacy_flow(src_ip="2001:db8::1")) is None
    assert module.to_flow_v1(legacy_flow(proto="ipv6-icmp")) is None


def test_capture_service_direction_covers_all_three_cases() -> None:
    module = load_capture_service()
    assert module.direction_of("10.0.0.5", "10.0.0.9") == "internal"
    assert module.direction_of("10.0.0.5", "8.8.8.8") == "outbound"
    assert module.direction_of("8.8.8.8", "10.0.0.5") == "inbound"


def test_zeek_conn_row_is_valid_flow_v1() -> None:
    zeek = load_bridge("zeek_bridge.py")
    row = {
        "ts": "1792000000.5",
        "id.orig_h": "10.0.0.5",
        "id.resp_h": "8.8.8.8",
        "id.orig_p": "51000",
        "id.resp_p": "443",
        "proto": "tcp",
        "orig_bytes": "100",
        "resp_bytes": "900",
        "orig_pkts": "5",
        "resp_pkts": "6",
        "duration": "1.2",
        "history": "ShADadFf",
        "service": "ssl",
        "conn_state": "SF",
    }
    out = zeek.to_flow_v1(zeek.parse_conn(row))
    assert out is not None
    FlowRecordIn.model_validate(out)


def test_suricata_flow_event_is_valid_flow_v1() -> None:
    suricata = load_bridge("suricata_bridge.py")
    event = {
        "src_ip": "10.0.0.5",
        "dest_ip": "8.8.8.8",
        "src_port": 51000,
        "dest_port": 443,
        "proto": "TCP",
        "bytes_toserver": 100,
        "bytes_toclient": 900,
        "pkts_toserver": 5,
        "pkts_toclient": 6,
        "flow": {"duration": 1.2, "state": "established"},
        "timestamp": "2026-10-17T10:00:00.123456+0000",
    }
    out = suricata.to_flow_v1(suricata.parse_flow(event))
    assert out is not None
    FlowRecordIn.model_validate(out)


def test_suricata_icmp_without_ports_is_valid_flow_v1() -> None:
    suricata = load_bridge("suricata_bridge.py")
    event = {
        "src_ip": "10.0.0.5",
        "dest_ip": "10.0.0.9",
        "proto": "ICMP",
        "bytes_toserver": 84,
        "bytes_toclient": 84,
        "pkts_toserver": 1,
        "pkts_toclient": 1,
        "flow": {"duration": 0.0},
        "timestamp": "2026-10-17T10:00:00+0000",
    }
    out = suricata.to_flow_v1(suricata.parse_flow(event))
    assert out is not None
    FlowRecordIn.model_validate(out)


def test_tcpdump_address_keeps_the_host_and_the_port() -> None:
    tcpdump = load_bridge("tcpdump_bridge.py")
    parsed = tcpdump.parse_tcpdump_line(
        "1792000000.123 IP 10.0.0.5.443 > 10.0.0.9.80: Flags [S], length 0"
    )
    assert parsed is not None
    record = parsed["record"]
    assert (record["src_ip"], record["src_port"]) == ("10.0.0.5", 443)
    assert (record["dst_ip"], record["dst_port"]) == ("10.0.0.9", 80)
    out = tcpdump.to_flow_v1(record)
    assert out is not None
    FlowRecordIn.model_validate(out)


def test_tshark_numeric_protocol_is_mapped_to_a_name() -> None:
    tcpdump = load_bridge("tcpdump_bridge.py")
    parsed = tcpdump.parse_tshark_line(
        "1792000000.1\t10.0.0.5\t8.8.8.8\t51000\t443\t6\t60\t1\t0\t0\t0\t0"
    )
    assert parsed is not None
    out = tcpdump.to_flow_v1(parsed["record"])
    assert out is not None
    assert out["protocol"] == "tcp"
    FlowRecordIn.model_validate(out)


# ── capture to ingest, and on to the detection engine ───────────────────────────


@pytest.fixture
def ingest_client(settings: Settings) -> Any:
    from app.main import create_app

    auth = TokenService(SECRET)
    built = create_app(settings)
    built.state.token_service = auth
    return TestClient(built), auth


def _headers(auth: TokenService) -> dict[str, str]:
    pair = auth.issue("collector", "analyst")
    return {"Authorization": f"Bearer {pair.access_token}", "Content-Type": "application/x-ndjson"}


def test_capture_batch_is_accepted_by_ingest(ingest_client: Any) -> None:
    client, auth = ingest_client
    module = load_capture_service()
    flows = [legacy_flow(ts=1_792_000_000.0 + i, dst_port=443 + i) for i in range(3)]
    body = "\n".join(json.dumps(module.to_flow_v1(f)) for f in flows).encode()
    response = client.post("/api/v1/ingest/flows", content=body, headers=_headers(auth))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["accepted"] == 3
    assert result["rejected"] == 0


def test_legacy_capture_batch_is_refused_as_before(ingest_client: Any) -> None:
    """Pins the original fault: the un-converted shape is what ingest refuses."""
    client, auth = ingest_client
    response = client.post(
        "/api/v1/ingest/flows",
        content=json.dumps(legacy_flow()).encode(),
        headers=_headers(auth),
    )
    assert response.json()["accepted"] == 0


def test_ingested_capture_flows_reach_the_detection_engine(ingest_client: Any) -> None:
    """Ingest -> engine.feed -> cycle -> model scorer, with the flows the endpoint stored."""
    client, auth = ingest_client
    scorer = FakeScorer(model_hit())
    engine = DetectionEngine(InMemoryAlertStore(), ml_scorer=scorer)
    client.app.state.detection_engine = engine
    module = load_capture_service()
    flows = [legacy_flow(ts=1_792_000_000.0 + i, dst_port=443 + i) for i in range(3)]
    body = "\n".join(json.dumps(module.to_flow_v1(f)) for f in flows).encode()
    response = client.post("/api/v1/ingest/flows", content=body, headers=_headers(auth))
    assert response.json()["accepted"] == 3
    engine._run_cycle()
    assert len(scorer.calls) == 1
    assert len(scorer.calls[0]) == 3
    assert engine.stats["total_alerts"] >= 1
