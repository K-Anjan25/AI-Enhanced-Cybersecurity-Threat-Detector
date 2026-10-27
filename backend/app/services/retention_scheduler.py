"""Run retention on a timer, so an unattended deployment still ages data out (NFR-05).

Before this, retention ran only when an operator called the run route. A deployment
nobody remembered to run kept every partition, and the 44 partitions past their window
accumulated silently. The scheduler closes that gap.

Behaviour:

* **Catches up shortly after start, then runs every interval.** The first run follows
  ``initial_delay_seconds`` (a minute by default), so a process restarted after days of
  downtime catches up within the minute rather than waiting a full interval. The delay
  also keeps a run from racing start-up work, which is what made the first version of
  this scheduler, which ran at the instant of start, perturb timing-sensitive tests.
* **A failed run is logged and the loop continues.** One bad run must not stop the next
  from happening; the failure is visible in logs and in the trail's absence of a record.
* **Stops promptly.** ``stop`` wakes the loop rather than waiting out the interval.

Several replicas each run their own scheduler. That is safe: partition drops are
``IF EXISTS`` and sweeps delete only what is still expired, so concurrent runs converge.
It is not free, since each replica writes its own trail record. A deployment that wants
one run per interval should run one replica of the scheduler, which is deployment
configuration and is named here rather than implied.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from app.core.logging import get_logger

__all__ = ["RetentionScheduler"]

_log = get_logger("aegis.retention")


class RetentionScheduler:
    """A daemon thread that calls ``run`` at start and then every ``interval_seconds``."""

    def __init__(
        self,
        run: Callable[[], object],
        *,
        interval_seconds: float,
        initial_delay_seconds: float = 60.0,
    ) -> None:
        """Create the scheduler; a non-positive interval is refused.

        A zero interval would spin, and disabling retention is the caller's decision,
        made by not creating a scheduler at all.
        """
        if interval_seconds <= 0:
            msg = "interval_seconds must be positive; disable retention by not scheduling it"
            raise ValueError(msg)
        self._run = run
        self._interval = interval_seconds
        self._initial_delay = max(0.0, initial_delay_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.runs = 0
        self.failures = 0

    def start(self) -> None:
        """Start the loop. Idempotent: a second call while running does nothing."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="retention-scheduler", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the loop to exit and wait up to ``timeout`` seconds for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _loop(self) -> None:
        if self._stop.wait(self._initial_delay):
            return
        while True:
            self._once()
            if self._stop.wait(self._interval):
                return

    def _once(self) -> None:
        try:
            self._run()
        except Exception:  # noqa: BLE001 -- a failed run must not kill the loop
            self.failures += 1
            _log.exception("retention_run_failed")
        else:
            self.runs += 1
