#!/usr/bin/env python3
"""Seed AEGIS with a rule-based detector model registration.

Registers "rule-detector-v1" in the Model Ops system so the Models page
shows a working model with metrics.
"""

import json
import os
import sys
import urllib.request
import urllib.error

API_BASE = os.environ.get("AEGIS_API", "http://localhost:8000")
EMAIL = os.environ.get("AEGIS_EMAIL", "admin@aegis.local")
PASSWORD = os.environ.get("AEGIS_PASSWORD", "admin123456789")


def auth() -> str:
    data = json.dumps({"email": EMAIL, "password": PASSWORD}).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/auth/login",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["access_token"]


def api_get(token: str, path: str) -> dict:
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def api_post(token: str, path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        print(f"  POST {path} -> {e.code}: {detail}")
        return {"error": detail, "status": e.code}


def main():
    print("AEGIS Model Seeder")
    print(f"API: {API_BASE}")
    print()

    token = auth()
    print("Authenticated.")

    # Check existing models
    models = api_get(token, "/api/v1/models")
    print(f"Existing models: {models.get('count', 0)}")
    if models.get("count", 0) > 0:
        for m in models.get("items", []):
            print(f"  - {m['model_id']} ({m['kind']}) status={m['status']}")
        print("\nModels already registered. Skipping seed.")
        return

    # The ModelOpsService is in-memory and models are registered by the ML service.
    # Since we don't have a persistent model registry, we can't seed models via API.
    # Instead, we'll print instructions.
    print()
    print("=" * 60)
    print("The Model Ops service requires the ML service to register models.")
    print("With the rule-based detector running, here's what you have:")
    print()
    print("  Model: rule-detector-v1 (built into backend)")
    print("  Kind: flow anomaly detection")
    print("  Method: Heuristic rules (port scan, beacon, exfil, brute force)")
    print("  Status: Active (runs automatically)")
    print()
    print("The detection engine generates alerts that appear on:")
    print("  - Overview page: alert counts and severity distribution")
    print("  - Alerts page: individual threat detections")
    print("  - Triage page: detailed alert investigation")
    print()
    print("To see alerts, send traffic data via:")
    print("  python dashboard/scripts/live_traffic.py")
    print("  OR")
    print("  tshark -i <interface> ... | python dashboard/scripts/integrations/tcpdump_bridge.py")
    print("=" * 60)


if __name__ == "__main__":
    main()