#!/usr/bin/env python3
"""End-to-end check of the Kafka flow path against a running stack (D-085).

Run it on the host after `docker compose up -d --build` in docker/ and wait for the
backend to be healthy. It needs only the Python standard library.

What it does:
  1. signs in as the bootstrap admin (the compose defaults, or the values you pass);
  2. ingests 120 flows from one source over HTTP (the ingest route publishes them to
     flows.raw and waits for broker acknowledgement);
  3. waits until the live consumer has scored two full 50-flow windows, which it
     reads from the backend's score-latency histogram on /metrics.

Exit 0 means: the broker accepted the records, the consumer read them, and the ML
service returned scores for them. Anything else prints which step failed and where
to look. It does not prove detection quality; that is the evaluation's job.

Usage:
    python scripts/kafka_smoke.py [--base http://localhost:8000]
                                  [--email admin@aegis.local] [--password ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

DEFAULT_EMAIL = "admin@aegis.local"
DEFAULT_PASSWORD = (
    "admin123456789"  # pragma: allowlist secret  # noqa: S105 - compose local default
)
SOURCE = "10.66.0.7"
FLOWS = 120
WINDOW = 50
WAIT_SECONDS = 120

_SCORED = re.compile(r"^aegis_score_latency_seconds_count\s+([0-9.eE+]+)", re.MULTILINE)


def _request(
    url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers or {})  # noqa: S310 - operator URL
    try:
        with urllib.request.urlopen(req, timeout=15) as response:  # noqa: S310 - operator URL
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, OSError) as exc:
        raise SystemExit(
            f"cannot reach {url}: {exc}. Is the stack up (docker compose ps)?"
        ) from exc


def _login(base: str, email: str, password: str) -> str:
    body = json.dumps({"email": email, "password": password}).encode()
    status, payload = _request(
        f"{base}/api/v1/auth/login", data=body, headers={"Content-Type": "application/json"}
    )
    if status != 200:
        raise SystemExit(f"login failed (HTTP {status}): check the admin email and password")
    return str(json.loads(payload)["access_token"])


def _flows_ndjson() -> bytes:
    start = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    lines = []
    for i in range(FLOWS):
        lines.append(
            json.dumps(
                {
                    "timestamp": (start + timedelta(seconds=i)).isoformat(),
                    "src_ip": SOURCE,
                    "dst_ip": "10.0.9.9",
                    "src_port": 40000 + i,
                    "dst_port": 443,
                    "protocol": "tcp",
                    "direction": "internal",
                    "packets": 10,
                    "src_packets": 5,
                    "dst_packets": 5,
                    "src_bytes": 500,
                    "dst_bytes": 500,
                    "duration": 1.0,
                }
            )
        )
    return "\n".join(lines).encode()


def _scored_windows(base: str) -> float:
    status, payload = _request(f"{base}/metrics")
    if status != 200:
        raise SystemExit(f"/metrics returned HTTP {status}")
    match = _SCORED.search(payload.decode())
    return float(match.group(1)) if match else 0.0


def main(argv: list[str] | None = None) -> int:
    """Run the smoke check; return 0 on pass, 1 on fail."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    args = parser.parse_args(argv)
    base = args.base.rstrip("/")

    print(f"1. sign in to {base}")
    token = _login(base, args.email, args.password)

    before = _scored_windows(base)
    print(f"2. ingest {FLOWS} flows from {SOURCE} (scored windows so far: {before:.0f})")
    status, payload = _request(
        f"{base}/api/v1/ingest/flows",
        data=_flows_ndjson(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/x-ndjson"},
    )
    if status != 200:
        print(f"   ingest failed (HTTP {status}): {payload[:300].decode(errors='replace')}")
        print("   A 503 here means the broker did not acknowledge: see the backend logs and")
        print("   `docker compose ps kafka`.")
        return 1
    result = json.loads(payload)
    print(f"   accepted={result.get('accepted')} rejected={result.get('rejected')}")
    if result.get("accepted") != FLOWS:
        print("   not every flow was accepted; the batch needs a closer look")
        return 1

    expected = before + FLOWS // WINDOW
    print(f"3. waiting up to {WAIT_SECONDS}s for the consumer to score {FLOWS // WINDOW} windows")
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        now = _scored_windows(base)
        if now >= expected:
            print(f"   scored windows: {now:.0f} (+{now - before:.0f})")
            print("PASS: broker accepted, consumer read, ML service scored.")
            return 0
        time.sleep(2)

    print(f"FAIL: only {_scored_windows(base) - before:.0f} of {FLOWS // WINDOW} windows scored.")
    print("   Check: `docker compose logs backend | grep kafka_scoring`")
    print("   and the ML service model: `curl localhost:8001/models`.")
    print("   A missing model shows as ml_window_scorer_refused / kafka_scoring_cycle_failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
