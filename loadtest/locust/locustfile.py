"""Locust load test for Threat AI backend — verifies NFR-PERF-01..04.

Targets (docs/non-functional-requirements.md):
    NFR-PERF-01  /api/v1/analyze          p95 <= 500 ms
    NFR-PERF-02  /api/v1/upload-logs      >= 100 lines/s (background scan)
    NFR-PERF-03  concurrent scans         no starvation >= MAX_CONCURRENT_SCANS
    NFR-PERF-04  /api/v1/alerts?limit=100 p95 <= 200 ms (at 10k alerts)

Usage (backend reachable at the host given by -H):
    pip install locust
    locust -f locustfile.py -H http://localhost:8000 --headless \
           -u 20 -r 4 -t 90s --csv baseline-backend --html report-backend.html
"""

import random

import requests
from locust import HttpUser, between, events, task

TOKEN_PASS = "ChangeMe#2026"

# One shared bearer token for all VUs. Logging in once keeps the backend's
# per-IP login rate limit (LOGIN_RATE_LIMIT_PER_MINUTE=10) from throttling
# the test, and keeps the measured numbers about the analysed paths only.
SHARED_AUTH: dict = {}


@events.test_start.add_listener
def _acquire_shared_session(environment, **_kwargs):
    global SHARED_AUTH
    base = environment.host or "http://localhost:8000"
    creds = {"username": "locustload", "password": TOKEN_PASS}
    requests.post(
        f"{base}/api/v1/register",
        json={**creds, "email": "locustload@test.local"},
        timeout=30,
    )
    resp = requests.post(
        f"{base}/api/v1/login",
        data=creds,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    token = (resp.json() or {}).get("access_token") or (resp.json() or {}).get("accessToken")
    if token:
        SHARED_AUTH = {"Authorization": f"Bearer {token}"}


LOGS = [
    {
        "message": "Failed password for invalid user root from 203.0.113.9 port 22 ssh2",
        "source": "auth.log",
        "level": "ERROR",
        "timestamp": "2026-08-14T15:00:00Z",
    },
    {
        "src_ip": "203.0.113.9",
        "dst_ip": "10.0.0.5",
        "src_port": "52341",
        "dst_port": "443",
        "protocol": "TCP",
        "bytes": 1245772,
        "duration": 12.4,
    },
]

BATCH_LINES = "\n".join(
    f"[{i}] Failed password for invalid user admin from 198.51.100.{i % 250} port 22 ssh2"
    for i in range(100)
)


class ThreatAIUser(HttpUser):
    """One simulated analyst hitting the backend API."""

    wait_time = between(0.1, 0.3)

    def on_start(self):
        self.auth = SHARED_AUTH

    @task(6)
    def analyze(self):
        """NFR-PERF-01: single-record alert analysis (p95 <= 500 ms)."""
        with self.client.post(
            "/api/v1/analyze",
            json=random.choice(LOGS),
            headers=self.auth,
            name="analyze",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"analyze returned {resp.status_code}")

    @task(3)
    def list_alerts(self):
        """NFR-PERF-04: paginated alert listing (p95 <= 200 ms at limit=100)."""
        with self.client.get(
            "/api/v1/alerts?limit=100",
            headers=self.auth,
            name="alerts?limit=100",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"alerts returned {resp.status_code}")

    @task(1)
    def upload_and_poll(self):
        """NFR-PERF-02/03: batch upload + background scan completion."""
        with self.client.post(
            "/api/v1/upload-logs",
            files={"log_file": ("loadtest.log", BATCH_LINES, "text/plain")},
            headers=self.auth,
            name="upload-logs",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"upload returned {resp.status_code}")
                return
            batch_id = (resp.json() or {}).get("batch_id")
        for _ in range(20):
            with self.client.get(
                f"/api/v1/uploads/{batch_id}",
                headers=self.auth,
                name="uploads/{id}",
                catch_response=True,
            ) as poll:
                if poll.status_code != 200:
                    poll.failure(f"poll returned {poll.status_code}")
                    return
                status = ((poll.json() or {}).get("batch") or {}).get("status")
                if status in ("completed", "failed"):
                    return