"""The shipped retention wiring, and the Kafka retention it depends on.

No database is needed. What these prove is what a deployment *without* one gets (an
empty catalog, a refusing runner, no sweeper), that the Kafka retention is applied on
create and re-asserted on an existing topic, and that a broker refusal is never a clean
start.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient
from pydantic import ValidationError

SECRET = "retention-wiring-secret-0123456789abcdef"


@pytest.fixture(autouse=True)
def _no_ambient_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings read the environment, so a shell with a database URL would leak into these."""
    monkeypatch.delenv("AEGIS_DATABASE_URL", raising=False)


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "env": "test",
        "service_name": "aegis-backend-test",
        "secret_key": SECRET,
        "log_level": "WARNING",
    }
    base.update(overrides)
    return Settings(**base)


def _admin_headers(app: Any) -> dict[str, str]:
    token_service: TokenService = app.state.token_service
    pair = token_service.issue("admin@corp", "admin")
    return {"Authorization": f"Bearer {pair.access_token}"}


# --- the shipped wiring without a database ------------------------------------


def test_without_a_database_the_catalog_is_empty_not_invented() -> None:
    """No database means no partitions; the plan must not show months never stored."""
    app = create_app(_settings())
    assert app.state.known_partitions() == set()
    assert app.state.retention_sweeper is None


def test_without_a_database_a_run_is_refused_rather_than_reported_clean() -> None:
    app = create_app(_settings())
    with (
        TestClient(app, raise_server_exceptions=True) as client,
        pytest.raises(RuntimeError, match="retention_sweeper is not configured"),
    ):
        client.post("/api/v1/retention/run", headers=_admin_headers(app))


def test_a_named_database_wires_the_real_catalog_and_runner() -> None:
    from app.services.retention_catalog import CatalogRunner

    app = create_app(_settings(database_url="postgresql+psycopg://u:p@127.0.0.1:1/none"))
    assert isinstance(app.state.partition_runner, CatalogRunner)
    assert callable(app.state.retention_sweeper)
    # Creating the app opens no connection, so the unreachable URL is not an error yet;
    # reading the catalog is, and it fails loudly rather than answering empty.
    with pytest.raises(Exception):  # noqa: B017 - the driver's connection error
        app.state.known_partitions()


# --- configuration -------------------------------------------------------------


def test_kafka_retention_may_not_outlive_the_raw_record_window() -> None:
    """FR-05: Kafka holding raw records longer than the policy promises is refused."""
    with pytest.raises(ValidationError, match="must not exceed"):
        _settings(kafka_retention_hours=24 * 31, retention_raw_records_days=30)


def test_kafka_retention_may_be_shorter_than_the_raw_window() -> None:
    settings = _settings(kafka_retention_hours=24, retention_raw_records_days=30)
    assert settings.kafka_retention_hours == 24


def test_kafka_retention_defaults_to_the_raw_window() -> None:
    assert _settings().kafka_retention_hours == 30 * 24


# --- the Kafka topic's retention -----------------------------------------------


class _Admin:
    """A fake admin client that scripts create and alter outcomes."""

    def __init__(self, creates: list[object], alters: list[object]) -> None:
        self.creates = creates
        self.alters = alters
        self.created: list[object] = []
        self.altered: list[object] = []

    def create_topics(self, topics: list[object]) -> object:
        self.created.append(topics)
        return self.creates.pop(0)

    def alter_configs(self, resources: list[object]) -> object:
        self.altered.append(resources)
        return self.alters.pop(0)

    def close(self) -> None:
        return None


def _ok_create(name: str) -> object:
    return SimpleNamespace(topic_errors=[(name, 0, "")])


def _ok_alter(name: str) -> object:
    return SimpleNamespace(resources=[(0, "", 2, name)])


def test_the_retention_is_set_on_create_and_asserted_on_an_existing_topic() -> None:
    from app.messaging.kafka_bus import KafkaBus

    admin = _Admin(
        creates=[SimpleNamespace(topic_errors=[("flows.raw", 36, "already exists")])],
        alters=[_ok_alter("flows.raw")],
    )
    bus = KafkaBus("kafka:9092", retention_ms=720 * 3_600_000, admin_factory=lambda: admin)
    bus.ensure_topic(sleep=lambda _s: None)

    (new_topics,) = admin.created
    (new_topic,) = new_topics  # type: ignore[misc]
    assert new_topic.topic_configs == {"retention.ms": str(720 * 3_600_000)}
    # The topic already existed, so create_topics would have left its retention alone:
    # the alter is what makes a restart with a changed setting take effect.
    (resources,) = admin.altered
    (resource,) = resources  # type: ignore[misc]
    assert resource.name == "flows.raw"
    assert resource.configs == {"retention.ms": str(720 * 3_600_000)}


def test_a_broker_that_refuses_the_retention_is_not_a_clean_start() -> None:
    from app.messaging.kafka_bus import KafkaBus, KafkaBusError

    refused = SimpleNamespace(resources=[(41, "invalid config", 2, "flows.raw")])
    admin = _Admin(
        creates=[_ok_create("flows.raw"), _ok_create("flows.raw")],
        alters=[refused, refused],
    )
    bus = KafkaBus("kafka:9092", retention_ms=1000, admin_factory=lambda: admin)
    with pytest.raises(KafkaBusError, match="could not create topic"):
        bus.ensure_topic(attempts=2, sleep=lambda _s: None)


def test_no_retention_setting_leaves_the_topic_configuration_alone() -> None:
    from app.messaging.kafka_bus import KafkaBus

    admin = _Admin(creates=[_ok_create("flows.raw")], alters=[])
    KafkaBus("kafka:9092", admin_factory=lambda: admin).ensure_topic(sleep=lambda _s: None)
    assert admin.altered == []


def test_a_non_positive_retention_is_refused_at_construction() -> None:
    from app.messaging.kafka_bus import KafkaBus

    with pytest.raises(ValueError, match="retention_ms"):
        KafkaBus("kafka:9092", retention_ms=0)


# --- the sweep's allowlist -----------------------------------------------------


def test_the_sweep_refuses_a_table_outside_its_allowlist() -> None:
    from datetime import UTC, datetime

    from app.services.retention_catalog import sweep_expired_rows

    with pytest.raises(ValueError, match="not a row-swept table"):
        sweep_expired_rows(
            None,  # type: ignore[arg-type] - refused before any engine is used
            cutoff=datetime.now(UTC),
            tables={"audit_log": "timestamp"},
        )
