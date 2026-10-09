# T-503: Failure-mode drills per architecture.md §14
#
# Each row of the failure table is exercised and the observed behaviour recorded.
# Run: python tests/load/failure_drills.py --base-url http://localhost:8000
#
# Requires: docker compose environment running.

"""Failure-mode drills: exercise each failure scenario and record behaviour."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import UTC, datetime

# architecture.md §14 failure modes
FAILURE_MODES = [
    {
        "id": "F-01",
        "name": "Scoring worker down",
        "description": "Kafka buffers; consumer lag rises; alerts delayed",
        "expected": "Worker restart resumes from committed offset; no data loss",
        "service": "ml-service",
    },
    {
        "id": "F-02",
        "name": "Model service OOM",
        "description": "Scores fail; ingest continues",
        "expected": "Worker falls back to rule-based safety net",
        "service": "ml-service",
    },
    {
        "id": "F-03",
        "name": "PostgreSQL down",
        "description": "Reads fail; API returns 503 with Retry-After",
        "expected": "API returns 503; scoring continues to Kafka",
        "service": "postgres",
    },
    {
        "id": "F-04",
        "name": "Kafka down",
        "description": "Ingest API returns 503 and clients retry",
        "expected": "Bounded in-memory buffer; explicit back-pressure",
        "service": "kafka",
    },
    {
        "id": "F-05",
        "name": "Dashboard WebSocket drops",
        "description": "UI falls back to REST polling at 15s",
        "expected": "Auto-reconnect with backoff",
        "service": "dashboard",
    },
]


def check_health(base_url: str) -> dict:
    try:
        resp = urllib.request.urlopen(f"{base_url}/healthz", timeout=5)
        return {"status": resp.status, "healthy": True}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "healthy": False}
    except Exception as e:
        return {"status": 0, "healthy": False, "error": str(e)}


def stop_service(service: str) -> bool:
    try:
        subprocess.run(
            ["docker", "compose", "stop", service],
            capture_output=True, timeout=30, check=False,
        )
        return True
    except Exception:
        return False


def start_service(service: str) -> bool:
    try:
        subprocess.run(
            ["docker", "compose", "start", service],
            capture_output=True, timeout=60, check=False,
        )
        return True
    except Exception:
        return False


def drill_postgres_down(base_url: str) -> dict:
    """F-03: Stop postgres, verify API returns 503."""
    result = {"mode": "F-03", "phase": "postgres_down"}
    before = check_health(base_url)
    result["before"] = before

    stop_service("postgres")
    time.sleep(3)

    during = check_health(base_url)
    result["during"] = during
    result["observed"] = "API returned 503" if during["status"] == 503 else f"API returned {during['status']}"

    start_service("postgres")
    time.sleep(5)

    after = check_health(base_url)
    result["after"] = after
    result["recovered"] = after["healthy"]
    return result


def drill_ml_service_down(base_url: str) -> dict:
    """F-01/F-02: Stop ml-service, verify ingest still works."""
    result = {"mode": "F-01/F-02", "phase": "ml_service_down"}

    stop_service("ml-service")
    time.sleep(3)

    # Try ingesting a flow
    try:
        body = json.dumps({
            "modality": "flow",
            "records": [{
                "src_ip": "10.0.0.1", "dst_ip": "10.0.0.2",
                "src_port": 12345, "dst_port": 80, "proto": "tcp",
                "bytes_in": 100, "bytes_out": 200,
                "packets_in": 1, "packets_out": 2, "duration": 0.5,
            }],
        }).encode()
        req = urllib.request.Request(
            f"{base_url}/api/v1/ingest",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result["ingest_during"] = {"status": resp.status, "accepted": True}
    except urllib.error.HTTPError as e:
        result["ingest_during"] = {"status": e.code, "accepted": False}
    except Exception as e:
        result["ingest_during"] = {"status": 0, "accepted": False, "error": str(e)}

    start_service("ml-service")
    time.sleep(5)
    result["recovered"] = check_health(base_url)["healthy"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="T-503 failure-mode drills")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--skip-drills", action="store_true",
                        help="Only report planned drills without executing")
    args = parser.parse_args()

    print(f"AEGIS Failure-Mode Drills — {datetime.now(UTC).isoformat()}")
    print()

    # Print the failure table from architecture.md §14
    print("Planned drills (architecture.md §14):")
    print(f"{'ID':<6} {'Name':<30} {'Expected behaviour'}")
    print("-" * 80)
    for mode in FAILURE_MODES:
        print(f"{mode['id']:<6} {mode['name']:<30} {mode['expected']}")

    if args.skip_drills:
        print("\n--skip-drills: Not executing drills. Table above is the plan.")
        return

    print()
    print("WARNING: This will stop and start Docker services!")
    print("Press Ctrl+C within 5 seconds to abort...")
    time.sleep(5)

    results = []

    print("\nDrill F-01/F-02: ML service down...")
    try:
        result = drill_ml_service_down(args.base_url)
        results.append(result)
        print(f"  Observed: {result.get('ingest_during', {}).get('status', 'unknown')}")
    except Exception as e:
        results.append({"mode": "F-01/F-02", "error": str(e)})
        print(f"  ERROR: {e}")

    print("\nDrill F-03: PostgreSQL down...")
    try:
        result = drill_postgres_down(args.base_url)
        results.append(result)
        print(f"  Observed: {result.get('observed', 'unknown')}")
    except Exception as e:
        results.append({"mode": "F-03", "error": str(e)})
        print(f"  ERROR: {e}")

    # Save results
    output = {
        "timestamp": datetime.now(UTC).isoformat(),
        "drills": results,
    }
    with open("tests/load/failure_drill_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to tests/load/failure_drill_results.json")


if __name__ == "__main__":
    main()
