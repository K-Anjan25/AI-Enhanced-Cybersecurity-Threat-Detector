"""PRD section 8: median analyst time-to-verdict <= 60 s.

The overview used to report only the mean. A mean is pulled far past the target
by one alert left open for hours, so the median is the statistic under test here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.overview import _mean_time_to_verdict, _median_time_to_verdict

T0 = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


def _row(seconds: float | None, *, verdict: str | None = "true_positive") -> SimpleNamespace:
    verdict_at = None if seconds is None else T0 + timedelta(seconds=seconds)
    return SimpleNamespace(verdict=verdict, verdict_at=verdict_at, created_at=T0)


def test_median_ignores_one_long_outlier_that_drags_the_mean() -> None:
    rows = [_row(10), _row(20), _row(30), _row(40), _row(7200)]

    mean, count = _mean_time_to_verdict(rows)
    median = _median_time_to_verdict(rows)

    assert count == 5
    assert mean is not None and mean > 60  # the mean is the number that misleads
    assert median == 30  # the median is what the PRD target is about


def test_unrecorded_and_negative_verdicts_are_left_out() -> None:
    rows = [_row(None, verdict=None), _row(-5), _row(12), _row(18)]

    assert _median_time_to_verdict(rows) == 15


def test_no_verdicts_means_no_median() -> None:
    assert _median_time_to_verdict([_row(None, verdict=None)]) is None
