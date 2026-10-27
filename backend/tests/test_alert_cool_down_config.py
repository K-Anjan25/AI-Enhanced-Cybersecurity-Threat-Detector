"""FR-15: the alert cool-down is a setting, and the setting reaches the correlator.

The policy itself (a repeat inside the window is absorbed, a closed case is not a
target) is covered in ``test_correlator.py``. These tests cover the part that was
missing: the default is 15 minutes, an operator can change it through configuration,
and the production wiring passes it into the correlator it builds.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import app.pipeline as pipeline_module
import app.services.kafka_pipeline as kafka_pipeline
import pytest
from app.core.config import Environment, Settings
from app.services.correlator import CorrelatorConfig
from pydantic import ValidationError

SECRET = "K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu"  # pragma: allowlist secret


def _settings(**overrides: Any) -> Settings:
    return Settings(env=Environment.TEST, secret_key=SECRET, **overrides)


def test_default_cool_down_is_fifteen_minutes() -> None:
    assert _settings().alert_cool_down_minutes == 15


def test_cool_down_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEGIS_ALERT_COOL_DOWN_MINUTES", "5")
    monkeypatch.setenv("AEGIS_SECRET_KEY", SECRET)
    assert Settings(env=Environment.TEST).alert_cool_down_minutes == 5


@pytest.mark.parametrize("bad", [0, -1, 1441])
def test_cool_down_outside_bounds_is_refused(bad: int) -> None:
    with pytest.raises(ValidationError):
        _settings(alert_cool_down_minutes=bad)


def test_production_wiring_passes_the_configured_cool_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_build_pipeline(*_args: Any, **kwargs: Any) -> object:
        seen.update(kwargs)
        raise _Stop

    class _Stop(Exception):
        pass

    monkeypatch.setattr(pipeline_module, "build_pipeline", fake_build_pipeline)
    cool_down = timedelta(minutes=_settings(alert_cool_down_minutes=7).alert_cool_down_minutes)

    with pytest.raises(_Stop):
        kafka_pipeline.build_kafka_pipeline(
            bootstrap_servers="unused:9092",
            ml_client=object(),
            alerts=object(),
            hub=None,
            registry=None,
            bus=_FakeBus(),  # type: ignore[arg-type]
            cool_down=cool_down,
        )

    config = seen["correlator_config"]
    assert isinstance(config, CorrelatorConfig)
    assert config.cool_down == timedelta(minutes=7)


def test_no_cool_down_argument_keeps_the_correlator_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class _Stop(Exception):
        pass

    def fake_build_pipeline(*_args: Any, **kwargs: Any) -> object:
        seen.update(kwargs)
        raise _Stop

    monkeypatch.setattr(pipeline_module, "build_pipeline", fake_build_pipeline)
    with pytest.raises(_Stop):
        kafka_pipeline.build_kafka_pipeline(
            bootstrap_servers="unused:9092",
            ml_client=object(),
            alerts=object(),
            hub=None,
            registry=None,
            bus=_FakeBus(),  # type: ignore[arg-type]
        )
    assert seen["correlator_config"] is None
    assert CorrelatorConfig().cool_down == timedelta(minutes=15)


class _FakeBus:
    """The three things ``build_kafka_pipeline`` reads from a bus before it stops."""

    partitions = 6
