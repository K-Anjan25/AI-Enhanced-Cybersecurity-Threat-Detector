"""Shared fixtures for the backend test suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.core.config import Environment, Settings
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def settings() -> Settings:
    """Return settings that never depend on the ambient environment (R-83)."""
    return Settings(
        env=Environment.TEST,
        service_name="aegis-backend-test",
        secret_key="test-secret-key-that-is-long-enough-0123456789",
        log_level="WARNING",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """Yield a test client bound to an isolated application instance."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client
