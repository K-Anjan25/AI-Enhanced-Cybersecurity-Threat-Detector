"""Health and readiness logic.

Pure business logic: this module must not import FastAPI (rule R-15) so it can
be exercised without an HTTP server.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

ProbeStatus = Literal["ok", "degraded", "unavailable"]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Outcome of a single readiness probe."""

    name: str
    status: ProbeStatus
    detail: str = ""


class Probe(Protocol):
    """A zero-argument callable returning a :class:`ProbeResult`.

    Probes must be cheap and must never raise; a failing dependency is reported
    as ``unavailable``, not propagated as an exception (rule R-06).
    """

    def __call__(self) -> ProbeResult:
        """Return this probe's current assessment of its dependency."""
        ...


class ReadinessRegistry:
    """Collects the probes that decide whether this process can serve traffic.

    Dependencies register themselves at startup (PostgreSQL in T-301, the model
    service in T-307). With no probes registered the process reports ready,
    because nothing it depends on has been declared yet.
    """

    def __init__(self) -> None:
        """Create an empty registry; dependencies register at startup."""
        self._probes: dict[str, Probe] = {}

    def register(self, name: str, probe: Probe) -> None:
        """Register a probe under a unique name.

        Raises:
            ValueError: if a probe with that name is already registered. Silent
                shadowing of a probe would hide a real dependency failure.
        """
        if name in self._probes:
            raise ValueError(f"readiness probe {name!r} is already registered")
        self._probes[name] = probe

    @property
    def names(self) -> list[str]:
        """Return registered probe names in registration order."""
        return list(self._probes)

    def check_all(self) -> list[ProbeResult]:
        """Run every probe, converting unexpected exceptions into a result.

        A probe that raises is reported as ``unavailable`` with the exception
        type as detail. Readiness reporting must never itself become the failure.
        """
        results: list[ProbeResult] = []
        for name, probe in self._probes.items():
            try:
                results.append(probe())
            except Exception as exc:  # noqa: BLE001 - probe failures are data, not crashes
                results.append(
                    ProbeResult(name=name, status="unavailable", detail=type(exc).__name__)
                )
        return results


def overall_status(results: list[ProbeResult]) -> Literal["ready", "not_ready"]:
    """Aggregate probe results: any non-``ok`` probe makes the process not ready."""
    return "ready" if all(result.status == "ok" for result in results) else "not_ready"


def build_health(service: str, version: str, environment: str) -> dict[str, str]:
    """Build the liveness payload.

    Liveness answers "is the process running" and never consults dependencies:
    a database outage must not cause a restart loop.
    """
    return {"status": "ok", "service": service, "version": version, "environment": environment}


def build_readiness(
    service: str, version: str, registry: ReadinessRegistry
) -> tuple[dict[str, object], int]:
    """Build the readiness payload and the HTTP status code it should be served with.

    Returns a 503 status when the process is not ready so orchestrators stop
    routing traffic to it (NFR-03).
    """
    results = registry.check_all()
    status = overall_status(results)
    payload: dict[str, object] = {
        "status": status,
        "service": service,
        "version": version,
        "checks": [{"name": r.name, "status": r.status, "detail": r.detail} for r in results],
    }
    return payload, (200 if status == "ready" else 503)


HealthBuilder = Callable[[str, str, str], dict[str, str]]
