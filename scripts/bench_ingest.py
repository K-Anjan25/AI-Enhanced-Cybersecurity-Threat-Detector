#!/usr/bin/env python3
"""Measure sustained flow ingest over HTTP against a running backend (NFR-02).

This is the measurement the repository's k6 script (tests/load/k6_ingest.js) makes at
5,000 flows/s for 30 minutes. k6 is not always installable, so this script measures the
same endpoint with the standard library: N threads, each posting 1,000-record NDJSON
batches to ``POST /api/v1/ingest/flows`` for a fixed duration, and it reports what the
server accepted, not what was offered.

It records the numbers it sees and nothing more. The output is one JSON line, so a run
can be pasted into a release note unedited.

Usage:
    python scripts/bench_ingest.py --base http://127.0.0.1:8000 \
        --email admin@example.com --password '...' --seconds 30 --threads 8
"""

from __future__ import annotations

import argparse
import http.client
import json
import statistics
import threading
import time
from datetime import UTC, datetime
from urllib.parse import urlparse


def _record(minute: int, src_octet: int, seq: int) -> dict[str, object]:
    """One valid flow@1 record."""
    return {
        "timestamp": datetime(2026, 3, 15, 10, minute % 60, seq % 60, tzinfo=UTC).isoformat(),
        "src_ip": f"10.0.{src_octet % 250}.{1 + seq % 250}",
        "dst_ip": "10.0.0.2",
        "src_port": 1024 + seq % 60000,
        "dst_port": 80,
        "protocol": "tcp",
        "direction": "inbound",
        "packets": 10,
        "src_packets": 5,
        "dst_packets": 5,
        "src_bytes": 1000,
        "dst_bytes": 2000,
        "duration": 1.5,
    }


def _login(base: str, email: str, password: str) -> str:
    url = urlparse(base)
    conn = http.client.HTTPConnection(url.hostname or "127.0.0.1", url.port or 80, timeout=30)
    body = json.dumps({"email": email, "password": password})
    conn.request("POST", "/api/v1/auth/login", body, {"Content-Type": "application/json"})
    response = conn.getresponse()
    payload = json.loads(response.read() or b"{}")
    conn.close()
    if response.status != 200 or "access_token" not in payload:
        raise SystemExit(f"login failed: HTTP {response.status}")
    token: str = payload["access_token"]
    return token


def main() -> None:
    """Parse the flags, drive the load, and print one JSON result line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--batch", type=int, default=1000, help="records per request, max 1000")
    parser.add_argument(
        "--rate",
        type=float,
        default=0.0,
        help="offer this many records/s in total, paced across threads (0 = unpaced)",
    )
    args = parser.parse_args()
    if args.rate < 0:
        raise SystemExit("--rate must be zero or positive")
    if not 1 <= args.batch <= 1000:
        raise SystemExit("--batch must be 1..1000 (the ingest route's cap)")

    url = urlparse(args.base)
    # The access token expires (15 minutes by default), so a long run must log in again.
    # The first run of this script did not, and half its requests were refused with 401.
    auth = {"token": _login(args.base, args.email, args.password)}
    relogins = 0

    lock = threading.Lock()
    accepted = 0
    requests_ok = 0
    errors: dict[str, int] = {}
    latencies: list[float] = []
    deadline = time.monotonic() + args.seconds

    def nonlocal_relogin() -> None:
        nonlocal relogins
        relogins += 1

    def worker(worker_id: int) -> None:
        nonlocal accepted, requests_ok
        conn = http.client.HTTPConnection(url.hostname or "127.0.0.1", url.port or 80, timeout=60)
        seq = worker_id * 10_000_000
        period = args.batch * args.threads / args.rate if args.rate > 0 else 0.0
        due = time.monotonic()
        while time.monotonic() < deadline:
            if period:
                # Pace to the offered rate: sleep until this slot, so the load is the
                # rate asked for and not whatever the server lets through.
                wait = due - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                due += period
            lines = []
            for _ in range(args.batch):
                seq += 1
                lines.append(json.dumps(_record(seq // 1000, worker_id, seq)))
            body = ("\n".join(lines) + "\n").encode()
            started = time.perf_counter()
            try:
                token_used = auth["token"]
                headers = {
                    "Authorization": f"Bearer {token_used}",
                    "Content-Type": "application/x-ndjson",
                }
                conn.request("POST", "/api/v1/ingest/flows", body, headers)
                response = conn.getresponse()
                payload = response.read()
                elapsed = time.perf_counter() - started
                if response.status == 401:
                    # Refresh once per expiry: whichever worker sees the old token first logs in,
                    # and the others reuse the new one. Then the same batch is sent again.
                    with lock:
                        if auth["token"] == token_used:
                            auth["token"] = _login(args.base, args.email, args.password)
                            nonlocal_relogin()
                    headers["Authorization"] = f"Bearer {auth['token']}"
                    started = time.perf_counter()
                    conn.request("POST", "/api/v1/ingest/flows", body, headers)
                    response = conn.getresponse()
                    payload = response.read()
                    elapsed = time.perf_counter() - started
            except OSError as exc:
                with lock:
                    key = type(exc).__name__
                    errors[key] = errors.get(key, 0) + 1
                conn.close()
                conn = http.client.HTTPConnection(
                    url.hostname or "127.0.0.1", url.port or 80, timeout=60
                )
                continue
            with lock:
                latencies.append(elapsed)
                if response.status == 200:
                    requests_ok += 1
                    try:
                        accepted += int(json.loads(payload).get("accepted", 0))
                    except (ValueError, AttributeError):
                        accepted += args.batch
                else:
                    key = f"HTTP {response.status}"
                    errors[key] = errors.get(key, 0) + 1
        conn.close()

    started_at = time.monotonic()
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(args.threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.monotonic() - started_at

    total_requests = requests_ok + sum(errors.values())
    p95 = (
        statistics.quantiles(latencies, n=20)[18] * 1000
        if len(latencies) >= 20
        else (max(latencies) * 1000 if latencies else None)
    )
    print(
        json.dumps(
            {
                "endpoint": "POST /api/v1/ingest/flows",
                "threads": args.threads,
                "batch": args.batch,
                "wall_seconds": round(wall, 2),
                "requests": total_requests,
                "offered_records_per_second": args.rate or None,
                "relogins_after_401": relogins,
                "accepted_records": accepted,
                "accepted_records_per_second": round(accepted / wall, 1) if wall else 0.0,
                "p95_request_ms": round(p95, 1) if p95 is not None else None,
                "errors": errors,
                "error_rate": (
                    round(sum(errors.values()) / total_requests, 4) if total_requests else None
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
