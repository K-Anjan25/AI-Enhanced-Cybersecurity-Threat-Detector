"""Choosing a log read model, and saying so (T-419).

``store_requested`` is the whole decision, and it is deliberately *not* a probe: a
process that opened a connection at startup to find out whether it had a store would
dial a database in every test that builds an application, and would turn "is Postgres
up yet" into a reason for a different read model mid-flight. These tests pin the three
modes against the one input that varies -- whether the deployment named a URL.

``TailLogSource`` is the other half: the tail is unchanged, and every read it answers
carries the reason this deployment is reading memory instead of a table, because a
15-minute window that does not say why is indistinguishable from a store that lost its
data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.core.config import LogStoreMode, Settings
from app.schemas.ingest import LogLevel, LogRecordIn
from app.services.log_source import TailLogSource, store_requested, tail_reason
from app.services.log_tail import LogTail, LogWindow

SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
START = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
WINDOW = LogWindow(start=START, end=START + timedelta(minutes=5))


class TestWhichSourceAnswers:
    """``AUTO`` is a question about configuration, not a connection."""

    @pytest.mark.parametrize("named", [True, False])
    def test_on_always_uses_the_store(self, named: bool) -> None:
        assert store_requested(LogStoreMode.ON, database_url_named=named) is True

    @pytest.mark.parametrize("named", [True, False])
    def test_off_never_uses_the_store(self, named: bool) -> None:
        assert store_requested(LogStoreMode.OFF, database_url_named=named) is False

    def test_auto_uses_the_store_when_the_deployment_named_a_url(self) -> None:
        assert store_requested(LogStoreMode.AUTO, database_url_named=True) is True

    def test_auto_uses_the_tail_when_only_the_default_exists(self) -> None:
        """The default URL exists so alembic has something to dial.

        It must not silently move a process's read path onto a database.
        """
        assert store_requested(LogStoreMode.AUTO, database_url_named=False) is False

    def test_the_default_settings_are_auto_and_name_nothing(self) -> None:
        settings = Settings(env="test", service_name="aegis", secret_key=SECRET)

        assert settings.log_store is LogStoreMode.AUTO
        assert "database_url" not in settings.model_fields_set
        assert store_requested(settings.log_store, database_url_named=False) is False

    def test_a_named_url_flips_auto_by_itself(self) -> None:
        settings = Settings(
            env="test",
            service_name="aegis",
            secret_key=SECRET,
            # No credential half, and never dialled: the test only asks whether the
            # field was named rather than inherited from the default.
            database_url="postgresql+psycopg://aegis@localhost:5432/aegis",
        )

        assert "database_url" in settings.model_fields_set
        assert store_requested(settings.log_store, database_url_named=True) is True


class TestWhyTheTailAnswered:
    """Each reason names the setting that would change it."""

    def test_an_off_store_names_the_setting(self) -> None:
        assert "AEGIS_LOG_STORE is off" in tail_reason(LogStoreMode.OFF)

    def test_an_unnamed_url_names_the_variable_and_the_migration(self) -> None:
        reason = tail_reason(LogStoreMode.AUTO)

        assert "AEGIS_DATABASE_URL" in reason
        assert "alembic upgrade head" in reason

    def test_the_reasons_are_different_sentences(self) -> None:
        """An operator reading one of them needs the fix for *their* deployment."""
        assert tail_reason(LogStoreMode.OFF) != tail_reason(LogStoreMode.AUTO)

    def test_every_mode_has_a_sentence(self) -> None:
        for mode in LogStoreMode:
            assert tail_reason(mode).endswith(".")


class TestTheTailSource:
    """The adapter the routes are written against."""

    def build(self, *, reason: str = "a test reason") -> tuple[TailLogSource, LogTail]:
        """A tail with a line in it, wrapped as a source."""
        tail = LogTail(max_lines=10, max_age_seconds=900.0, clock=lambda: START)
        tail.append(
            [
                LogRecordIn(
                    schema_version="log@1",
                    timestamp=START + timedelta(seconds=5),
                    host="web-1",
                    service="api",
                    level=LogLevel.ERROR,
                    message="boom",
                    template_id="t-1",
                )
            ]
        )
        return TailLogSource(tail, reason=reason), tail

    def test_it_names_itself(self) -> None:
        source, _ = self.build()

        assert source.name == "tail"

    def test_its_span_bound_is_the_tails_retention(self) -> None:
        source, tail = self.build()

        assert source.max_span_seconds == tail.max_age_seconds == 900.0

    def test_it_exposes_the_tail_it_wraps(self) -> None:
        source, tail = self.build()

        assert source.tail is tail

    def test_a_read_carries_the_reason(self) -> None:
        source, _ = self.build(reason="because the store is off")

        payload = asyncio_run(source.clusters(WINDOW, limit=10))

        assert payload.source == "tail"
        assert payload.caveats[-1] == "because the store is off"

    def test_the_raw_line_read_carries_it_too(self) -> None:
        source, _ = self.build(reason="because the store is off")

        payload = asyncio_run(source.lines(WINDOW, limit=10))

        assert payload.source == "tail"
        assert payload.caveats[-1] == "because the store is off"

    def test_the_reason_does_not_accumulate_across_reads(self) -> None:
        """A screen that polled every 15 seconds must not grow a sentence each time."""
        source, _ = self.build(reason="once")

        first = asyncio_run(source.clusters(WINDOW, limit=10))
        second = asyncio_run(source.clusters(WINDOW, limit=10))

        assert first.caveats.count("once") == 1
        assert second.caveats.count("once") == 1

    def test_appending_goes_through_to_the_tail(self) -> None:
        source, tail = self.build()

        kept = asyncio_run(
            source.append(
                [
                    LogRecordIn(
                        schema_version="log@1",
                        timestamp=START,
                        host="web-2",
                        service="api",
                        level=LogLevel.INFO,
                        message="second",
                        template_id="t-2",
                    )
                ]
            )
        )

        assert kept == 1
        assert len(tail) == 2

    def test_the_fold_is_the_tails_own(self) -> None:
        """The adapter adds a sentence; it does not change a count."""
        source, _ = self.build()

        payload = asyncio_run(source.clusters(WINDOW, limit=10))

        assert payload.lines_seen == 1
        assert [cluster.key for cluster in payload.clusters] == ["t-1"]


def asyncio_run(coro: object) -> object:
    """Drive one coroutine from a sync test, as the rest of the suite does."""
    import asyncio

    return asyncio.run(coro)  # type: ignore[arg-type]
