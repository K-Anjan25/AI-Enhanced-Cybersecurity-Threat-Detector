"""The capture services refuse to start with the development default password.

Each guarded program is run as a subprocess with AEGIS_PASSWORD unset or set to the
default. The refusal message is asserted, so an argparse error cannot make these
tests pass by accident.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CAPTURE = Path(__file__).resolve().parents[1] / "app" / "services" / "capture"
REFUSAL = "refusing to start"
DEFAULT = "admin123456789"  # pragma: allowlist secret

BRIDGE_ARGS = ["--api", "http://127.0.0.1:9", "--email", "admin@aegis.local"]


def _env(password: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "AEGIS_PASSWORD"}
    if password is not None:
        env["AEGIS_PASSWORD"] = password
    return env


def _run(argv: list[str], password: str | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        env=_env(password),
        cwd=CAPTURE,
        timeout=30,
        check=False,
    )


PASSWORDS = [None, "", DEFAULT]


@pytest.mark.parametrize("password", PASSWORDS)
def test_capture_service_refuses(password: str | None) -> None:
    result = _run([sys.executable, "capture_service.py"], password)
    assert result.returncode == 2, result.stderr
    assert REFUSAL in result.stderr


@pytest.mark.parametrize("script", ["zeek_bridge.py", "suricata_bridge.py", "tcpdump_bridge.py"])
@pytest.mark.parametrize("password", PASSWORDS)
def test_bridges_refuse(script: str, password: str | None) -> None:
    argv = [sys.executable, f"bridges/{script}", *BRIDGE_ARGS]
    result = _run(argv, password)
    assert result.returncode == 2, result.stderr
    assert REFUSAL in result.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize(
    "script", ["zeek_entrypoint.sh", "suricata_entrypoint.sh", "tshark_entrypoint.sh"]
)
@pytest.mark.parametrize("password", PASSWORDS)
def test_entrypoints_refuse_before_starting(script: str, password: str | None) -> None:
    result = _run(["bash", script], password)
    assert result.returncode == 2, result.stderr
    assert REFUSAL in result.stderr
    # Nothing should have been started, so no interface banner is printed.
    assert "Interface:" not in result.stdout


def test_compose_has_no_default_capture_password() -> None:
    compose = (CAPTURE.parents[3] / "docker" / "docker-compose.yml").read_text()
    assert "AEGIS_PASSWORD: ${AEGIS_BOOTSTRAP_ADMIN_PASSWORD:-}" in compose
    assert "AEGIS_PASSWORD: ${AEGIS_BOOTSTRAP_ADMIN_PASSWORD:-admin123456789}" not in compose
