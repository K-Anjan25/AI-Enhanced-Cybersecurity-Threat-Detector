"""Desired packet-capture state, held by the control plane.

The control plane records *what should run*: whether capture is on, and which
engines it should use. A sensor reads that state and reconciles itself to it. The
sensor is not started or stopped from here, because doing that would mean giving
the API a handle on the host's container runtime.

The state is process-local and makes no persistence claim, like the other in-memory
stores in this service. A restart resets it to stopped.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from threading import RLock

#: The engines the capture image can run. Anything else is refused.
ENGINES: frozenset[str] = frozenset({"zeek", "suricata", "tshark"})
#: The default engine set, matching the capture entrypoint's default.
DEFAULT_ENGINES: tuple[str, ...] = ("zeek", "suricata")


class InvalidCaptureRequest(ValueError):
    """Raised for an unknown engine or a start request with no engine."""


@dataclass(frozen=True)
class CaptureState:
    """What capture should be doing, and who last changed it."""

    running: bool
    engines: tuple[str, ...]
    version: int
    changed_by: str | None
    changed_at: datetime | None


def validate_engines(engines: Iterable[str]) -> tuple[str, ...]:
    """Normalise and check engine names, dropping duplicates and keeping order."""
    chosen: list[str] = []
    for raw in engines:
        name = raw.strip().lower()
        if name not in ENGINES:
            raise InvalidCaptureRequest(
                f"unknown engine {raw!r}; allowed engines are {sorted(ENGINES)}"
            )
        if name not in chosen:
            chosen.append(name)
    return tuple(chosen)


class CaptureControl:
    """Holds the desired capture state, with a version that increases on every change."""

    def __init__(self) -> None:
        """Start stopped, with the default engine set selected."""
        self._lock = RLock()
        self._state = CaptureState(
            running=False,
            engines=DEFAULT_ENGINES,
            version=0,
            changed_by=None,
            changed_at=None,
        )

    def get(self) -> CaptureState:
        """The current desired state."""
        with self._lock:
            return self._state

    def set(
        self,
        *,
        running: bool,
        engines: Iterable[str],
        actor: str,
        at: datetime,
    ) -> CaptureState:
        """Replace the desired state.

        Raises:
            InvalidCaptureRequest: for an unknown engine, or for starting with none.
        """
        chosen = validate_engines(engines)
        if running and not chosen:
            raise InvalidCaptureRequest("choose at least one engine to start capture")
        with self._lock:
            self._state = CaptureState(
                running=running,
                engines=chosen,
                version=self._state.version + 1,
                changed_by=actor,
                changed_at=at,
            )
            return self._state
