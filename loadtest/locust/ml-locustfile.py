"""Locust load test for the ML service — verifies NFR-PERF-05.

Target:
    NFR-PERF-05  ml-service /predict/*  >= 50 predictions/s per replica

Usage (ml-service reachable at the host given by -H):
    pip install locust
    locust -f ml-locustfile.py -H http://localhost:8001 --headless \
           -u 50 -r 10 -t 30s --csv baseline-ml --html report-ml.html
"""

import json

from locust import HttpUser, constant, task

LOG_SAMPLE = {
    "message": "Failed password for invalid user root from 203.0.113.9 port 22 ssh2",
    "source": "auth.log",
    "level": "ERROR",
    "timestamp": "2026-08-14T15:00:00Z",
}


class MLUser(HttpUser):
    """Steady-arrival predictor hitting /predict/log."""

    # No think time: constant-arrival throughput, not pacing.
    wait_time = constant(0)

    @task
    def predict_log(self):
        with self.client.post(
            "/predict/log",
            json=LOG_SAMPLE,
            headers={"Content-Type": "application/json"},
            name="predict/log",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"predict/log returned {resp.status_code}")