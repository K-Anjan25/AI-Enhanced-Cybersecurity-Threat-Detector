"""The ML service must import, start and answer without torch (the [training] extra).

Regression: flownet_scorer imported torch at module level, so the service image, which
installs core dependencies only, crashed on import. The check runs in a fresh interpreter
with torch blocked, because the test session itself may have torch installed.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

SCRIPT = textwrap.dedent("""
    import sys
    sys.modules["torch"] = None  # any `import torch` now raises ImportError
    import os
    os.environ["AEGIS_ML_SERVICE_TOKEN"] = "no-torch-token-with-enough-entropy-2026"  # pragma: allowlist secret
    from fastapi.testclient import TestClient
    from aegis_ml.serving.app import app
    client = TestClient(app, headers={"X-AEGIS-Service-Token": "no-torch-token-with-enough-entropy-2026"})  # pragma: allowlist secret
    assert client.get("/internal/healthz").status_code == 200
    assert client.get("/models").status_code == 200
    flow = {
        "schema_version": "flow@1", "timestamp": "2026-10-17T10:00:00Z",
        "src_ip": "10.0.0.5", "dst_ip": "8.8.8.8", "src_port": 1, "dst_port": 443,
        "protocol": "tcp", "direction": "outbound", "packets": 2, "src_packets": 1,
        "dst_packets": 1, "src_bytes": 1, "dst_bytes": 1, "duration": 0.1,
    }
    response = client.post("/score/windows", json={"flows": [flow, flow]})
    assert response.status_code == 503, response.text
    assert "torch" in response.json()["detail"]["reason"], response.text
    print("ok")
    """)


def test_service_serves_without_torch(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_FLOWNET_CHECKPOINT_DIR", str(tmp_path / "absent"))
    result = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("ok")
