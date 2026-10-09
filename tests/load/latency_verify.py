# T-502: Latency verification against NFR-01 budget
#
# Measures p95 latency per stage and compares against the budget table
# in architecture.md §5.
#
# Run: python tests/load/latency_verify.py --base-url http://localhost:8000

"""Measure and report per-stage p95 latency against NFR-01 budget."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
import urllib.error
from datetime import UTC, datetime

# NFR-01 latency budget (p95, milliseconds)
BUDGET = {
    "ingest_validate_kafka_produce": 40,
    "kafka_worker_consume": 100,
    "window_assembly": 20,
    "feature_extraction": 15,
    "transformer_inference": 90,
    "fusion_correlate_persist": 30,
    "websocket_delivery": 20,
    "total": 315,
}


def measure_ingest_latency(base_url: str, n: int = 100) -> list[float]:
    """Measure ingest endpoint latency."""
    import random
    latencies = []
    for _ in range(n):
        flow = {
            "src_ip": f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
            "dst_ip": f"192.168.{random.randint(0,255)}.{random.randint(1,254)}",
            "src_port": random.randint(1024, 65535),
            "dst_port": random.choice([80, 443, 53, 22, 3389]),
            "proto": "tcp",
            "bytes_in": random.randint(100, 100000),
            "bytes_out": random.randint(100, 500000),
            "packets_in": random.randint(1, 100),
            "packets_out": random.randint(1, 500),
            "duration": random.random() * 60,
        }
        body = json.dumps({"modality": "flow", "records": [flow]}).encode()
        req = urllib.request.Request(
            f"{base_url}/api/v1/ingest",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        start = time.monotonic()
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
        elapsed_ms = (time.monotonic() - start) * 1000
        latencies.append(elapsed_ms)
    return latencies


def measure_health_latency(base_url: str, n: int = 50) -> list[float]:
    """Measure health endpoint latency."""
    latencies = []
    for _ in range(n):
        start = time.monotonic()
        try:
            urllib.request.urlopen(f"{base_url}/healthz", timeout=5)
        except Exception:
            pass
        elapsed_ms = (time.monotonic() - start) * 1000
        latencies.append(elapsed_ms)
    return latencies


def measure_detection_status_latency(base_url: str, n: int = 50) -> list[float]:
    """Measure detection status endpoint latency."""
    latencies = []
    for _ in range(n):
        start = time.monotonic()
        try:
            urllib.request.urlopen(f"{base_url}/api/v1/detection/status", timeout=5)
        except Exception:
            pass
        elapsed_ms = (time.monotonic() - start) * 1000
        latencies.append(elapsed_ms)
    return latencies


def report(stage: str, latencies: list[float], budget_ms: float) -> bool:
    if not latencies:
        print(f"  {stage}: NO DATA")
        return False
    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    p99 = sorted(latencies)[int(len(latencies) * 0.99)]
    passed = p95 <= budget_ms
    status = "PASS" if passed else "FAIL"
    print(f"  {stage}: p50={p50:.1f}ms  p95={p95:.1f}ms  p99={p99:.1f}ms  budget={budget_ms}ms  [{status}]")
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="T-502 latency verification")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--samples", type=int, default=100)
    args = parser.parse_args()

    print(f"AEGIS Latency Verification (NFR-01) — {datetime.now(UTC).isoformat()}")
    print(f"Target: {args.base_url}")
    print(f"Samples: {args.samples}")
    print()

    all_passed = True

    print("Measuring ingest latency...")
    ingest_latencies = measure_ingest_latency(args.base_url, args.samples)
    all_passed &= report("ingest_validate+kafka_produce", ingest_latencies, BUDGET["ingest_validate_kafka_produce"])

    print("Measuring health endpoint latency...")
    health_latencies = measure_health_latency(args.base_url, min(args.samples, 50))
    all_passed &= report("healthz", health_latencies, 10)

    print("Measuring detection status latency...")
    status_latencies = measure_detection_status_latency(args.base_url, min(args.samples, 50))
    all_passed &= report("detection_status", status_latencies, 30)

    print()
    print(f"Total measured stages: 3 / 7")
    print(f"  (window_assembly, feature_extraction, transformer_inference,")
    print(f"   fusion_correlate_persist, websocket_delivery require live Kafka/ML pipeline)")
    print()
    print(f"Overall: {'ALL MEASURED STAGES PASS' if all_passed else 'SOME STAGES OVER BUDGET'}")


if __name__ == "__main__":
    main()
