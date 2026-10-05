"""The process entry point must fail with an actionable message, not a traceback.

T-002 acceptance criterion: "a missing required env var fails startup with a
named error, not a stack trace".
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str], extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run a command in a clean subprocess with no ambient AEGIS_* variables."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AEGIS_")}
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, *args],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_missing_secret_key_exits_nonzero_naming_the_variable() -> None:
    """Startup refuses to run and says exactly which variable to set."""
    result = _run(["-m", "app.main"], {})

    assert result.returncode == 1
    assert "AEGIS_SECRET_KEY" in result.stderr
    assert "Traceback" not in result.stderr


def test_invalid_log_level_exits_nonzero_naming_the_variable() -> None:
    """A bad value is reported as a named configuration problem too."""
    result = _run(
        ["-m", "app.main"],
        {"AEGIS_SECRET_KEY": "K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu", "AEGIS_LOG_LEVEL": "VERBOSE"},
    )

    assert result.returncode == 1
    assert "AEGIS_LOG_LEVEL" in result.stderr
    assert "Traceback" not in result.stderr


def test_importing_the_module_does_not_require_configuration() -> None:
    """Import must be side-effect free so tests and tools can load it."""
    result = _run(["-c", "import app.main; print('imported')"], {})

    assert result.returncode == 0, result.stderr
    assert "imported" in result.stdout


def test_valid_configuration_builds_the_asgi_app() -> None:
    """With a real secret the app object resolves and is a FastAPI instance."""
    result = _run(
        ["-c", "from app.main import app; print(type(app).__name__)"],
        {"AEGIS_SECRET_KEY": "K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu", "AEGIS_ENV": "test"},
    )

    assert result.returncode == 0, result.stderr
    assert "FastAPI" in result.stdout
