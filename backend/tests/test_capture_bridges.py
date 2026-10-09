"""The capture bridges must accept exactly what their entrypoints pass them.

Regression: ``zeek_bridge.py`` failed at start-up with ``ambiguous option: --log
could match --log-dir, --log-type`` because an entrypoint passed an abbreviated
flag. These tests pin two things: every flag an entrypoint passes exists on the
bridge it feeds, and abbreviated flags are rejected rather than guessed at.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

CAPTURE = Path(__file__).resolve().parents[1] / "app" / "services" / "capture"
BRIDGES = CAPTURE / "bridges"

# entrypoint -> the bridge it pipes into
PIPELINES = {
    "zeek_entrypoint.sh": "zeek_bridge.py",
    "suricata_entrypoint.sh": "suricata_bridge.py",
    "tshark_entrypoint.sh": "tcpdump_bridge.py",
}


def _help(bridge: str) -> str:
    result = subprocess.run(
        [sys.executable, str(BRIDGES / bridge), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _entrypoint_flags(entrypoint: str, bridge: str) -> set[str]:
    """Return the ``--flag`` tokens on the bridge invocation in an entrypoint.

    The invocation is the ``python3 ... <bridge>`` line plus its backslash-continued
    argument lines.
    """
    lines = (CAPTURE / entrypoint).read_text().splitlines()
    flags: set[str] = set()
    for index, line in enumerate(lines):
        if bridge not in line or "python3" not in line:
            continue
        block = [line]
        while block[-1].rstrip().endswith("\\") and index + len(block) < len(lines):
            block.append(lines[index + len(block)])
        for part in block:
            flags.update(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", part))
        break
    return flags


@pytest.mark.parametrize("bridge", sorted(set(PIPELINES.values())))
def test_bridge_starts_and_documents_its_options(bridge: str) -> None:
    assert "--api" in _help(bridge)


@pytest.mark.parametrize(("entrypoint", "bridge"), sorted(PIPELINES.items()))
def test_entrypoint_passes_only_options_the_bridge_defines(entrypoint: str, bridge: str) -> None:
    help_text = _help(bridge)
    passed = _entrypoint_flags(entrypoint, bridge)
    assert passed, f"no flags found for {bridge} in {entrypoint}"
    missing = sorted(flag for flag in passed if flag not in help_text)
    assert not missing, f"{entrypoint} passes {missing}, which {bridge} does not define"


@pytest.mark.parametrize("bridge", sorted(set(PIPELINES.values())))
def test_abbreviated_option_is_rejected_not_guessed(bridge: str) -> None:
    result = subprocess.run(
        [sys.executable, str(BRIDGES / bridge), "--log", "conn"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 2
    assert "ambiguous" not in result.stderr
    assert "unrecognized arguments: --log" in result.stderr


CAPTURE_PYTHON = sorted(BRIDGES.glob("*.py"))


@pytest.mark.parametrize("path", CAPTURE_PYTHON, ids=lambda p: p.name)
def test_bridge_is_python_310_compatible(path: Path) -> None:
    """The capture images run Ubuntu 22.04's Python 3.10, not the backend's 3.11.

    Regression: ``from datetime import UTC`` is 3.11-only and crashed every
    bridge at import time. Parse with the 3.10 grammar, then reject the imports
    that parse but still fail on 3.10.
    """
    tree = ast.parse(path.read_text(), filename=str(path), feature_version=(3, 10))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "datetime":
            names = {alias.name for alias in node.names}
            assert "UTC" not in names, f"{path.name} imports datetime.UTC (Python 3.11+ only)"


def test_suricata_entrypoint_does_not_override_outputs_with_set() -> None:
    """Suricata 6 rejects ``--set outputs.eve-log.*``.

    ``outputs`` is a YAML list there, so the override fails with
    SC_ERR_INVALID_ARGUMENT and eve.json is never written.
    """
    text = (CAPTURE / "suricata_entrypoint.sh").read_text()
    assert "--set outputs." not in text
