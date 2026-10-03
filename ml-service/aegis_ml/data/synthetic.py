"""Deterministic synthetic telemetry generator (T-106).

The public datasets (UNSW-NB15, CIC-IDS2017) contain no genuine insider-threat
or long-period C2 beaconing behaviour, and neither can be fetched from an
allowlisted network. This generator fills that gap and doubles as the fixture
source for tests and demos.

Two rules make it trustworthy:

* **Deterministic (R-42).** The same seed always produces byte-identical output.
  Nothing here reads the wall clock, the environment, or global random state.
* **Labelled by construction.** Every record carries its attack family, so the
  supervision is exact rather than inferred.

What this is *not*: a model of real traffic. Distributional realism is limited,
and performance measured on synthetic data must never be reported as field
performance (R-74). Model cards must say so (T-214).
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from ipaddress import IPv4Address

from aegis_ml.data.records import Direction, FlowRecord, LogLevel, LogRecord, Protocol

#: Fixed epoch for generated timelines. Using a constant keeps output
#: reproducible; no record timestamp is ever derived from the current time.
EPOCH = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)


class Scenario(StrEnum):
    """Attack families the generator can produce, mapped to prd.md §3.1."""

    NORMAL = "normal"
    PORT_SCAN = "port_scan"  # T1 Reconnaissance
    DDOS = "ddos"  # T2 DoS / DDoS
    BRUTE_FORCE = "brute_force"  # T4 Credential abuse
    BEACONING = "beaconing"  # T6 C2
    EXFILTRATION = "exfiltration"  # T6 Exfiltration
    INSIDER_THREAT = "insider_threat"  # T5 Insider threat / privilege escalation


#: Label written onto every record a scenario produces.
LABELS: dict[Scenario, str] = {
    Scenario.NORMAL: "normal",
    Scenario.PORT_SCAN: "Reconnaissance",
    Scenario.DDOS: "DoS",
    Scenario.BRUTE_FORCE: "BruteForce",
    Scenario.BEACONING: "Beaconing",
    Scenario.EXFILTRATION: "Exfiltration",
    Scenario.INSIDER_THREAT: "InsiderThreat",
}

#: Internal hosts the generator invents traffic between.
INTERNAL_HOSTS = ("10.4.20.11", "10.4.20.12", "10.4.20.13", "10.4.20.14")
EXTERNAL_HOSTS = ("45.83.2.11", "91.204.14.7", "185.220.101.4")

WELL_KNOWN_PORTS = (22, 53, 80, 443, 993, 3306, 5432, 8080)

#: Insider activity is generated off-hours. EPOCH is 08:00, so +18 h is 02:00,
#: and the offset stays positive (see the guard in :func:`_flow`).
OFF_HOURS = timedelta(hours=18)

#: Internal servers a legitimate-but-curious employee would reach for.
INSIDER_TARGETS = ("10.4.20.90", "10.4.20.91")


@dataclass(frozen=True, slots=True)
class GenerationSpec:
    """What to generate. Fully determines the output when combined with a seed."""

    scenario: Scenario
    count: int
    seed: int
    start: datetime = EPOCH

    def __post_init__(self) -> None:
        """Reject a spec that cannot produce anything meaningful."""
        if self.count <= 0:
            raise ValueError(f"count must be positive, got {self.count}")
        if self.start.tzinfo is None:
            raise ValueError("start must be timezone-aware")


def _rng(spec: GenerationSpec) -> random.Random:
    """Return a private, seeded generator.

    ``random.Random`` is a local instance, so nothing here mutates global random
    state and no other module can perturb the sequence. A CSPRNG is deliberately
    not used: reproducibility is the requirement, not unpredictability.
    """
    return random.Random(spec.seed)  # noqa: S311 - determinism required, not crypto


def _flow(  # noqa: PLR0913 - a flow record is inherently a wide tuple
    spec: GenerationSpec,
    offset: float,
    src: str,
    dst: str,
    src_port: int,
    dst_port: int,
    *,
    protocol: Protocol = Protocol.TCP,
    direction: Direction = Direction.INTERNAL,
    service: str | None = None,
    state: str = "SF",
    packets: int = 10,
    src_bytes: int = 1200,
    dst_bytes: int = 3400,
    duration: float = 0.8,
    syn: int = 1,
    ack: int = 8,
    rst: int = 0,
    fin: int = 1,
) -> FlowRecord:
    """Build one record, splitting packet counts between the two directions.

    Raises:
        ValueError: if ``offset`` is negative. A generated timeline must never
            start before its declared start; failing loudly here stops a
            scenario builder from silently emitting pre-start records (R-06).
    """
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    src_packets = max(1, packets // 2)
    return FlowRecord(
        timestamp=spec.start + timedelta(seconds=offset),
        src_ip=IPv4Address(src),
        dst_ip=IPv4Address(dst),
        src_port=src_port,
        dst_port=dst_port,
        protocol=protocol,
        direction=direction,
        service=service,
        state=state,
        packets=packets,
        src_packets=src_packets,
        dst_packets=max(0, packets - src_packets),
        src_bytes=src_bytes,
        dst_bytes=dst_bytes,
        duration=duration,
        syn=syn,
        ack=ack,
        rst=rst,
        fin=fin,
        label=LABELS[spec.scenario],
    )


def _normal(spec: GenerationSpec) -> list[FlowRecord]:
    """Ordinary client/server traffic across well-known services."""
    rng = _rng(spec)
    flows: list[FlowRecord] = []
    for index in range(spec.count):
        src = rng.choice(INTERNAL_HOSTS)
        dst = rng.choice(EXTERNAL_HOSTS + INTERNAL_HOSTS)
        dst_port = rng.choice(WELL_KNOWN_PORTS)
        flows.append(
            _flow(
                spec,
                offset=index * rng.uniform(0.4, 2.5),
                src=src,
                dst=dst,
                src_port=rng.randint(49152, 65535),
                dst_port=dst_port,
                service=(
                    "http" if dst_port in (80, 8080) else "https" if dst_port == 443 else None
                ),
                packets=rng.randint(6, 40),
                src_bytes=rng.randint(400, 4000),
                dst_bytes=rng.randint(800, 60000),
                duration=round(rng.uniform(0.05, 4.0), 3),
            )
        )
    return flows


def _port_scan(spec: GenerationSpec) -> list[FlowRecord]:
    """One source sweeping many destination ports: half-open SYNs, no data.

    The signature feature extraction keys on (T-107) is a destination-port count
    far above baseline combined with a very high SYN ratio and near-zero payload.
    """
    rng = _rng(spec)
    src = rng.choice(INTERNAL_HOSTS)
    target = rng.choice(EXTERNAL_HOSTS)
    flows: list[FlowRecord] = []
    for index in range(spec.count):
        flows.append(
            _flow(
                spec,
                offset=index * 0.02,
                src=src,
                dst=target,
                src_port=rng.randint(49152, 65535),
                dst_port=1024 + index,
                state="S0",
                packets=1,
                src_bytes=60,
                dst_bytes=0,
                duration=0.001,
                syn=1,
                ack=0,
                rst=1,
                fin=0,
            )
        )
    return flows


def _ddos(spec: GenerationSpec) -> list[FlowRecord]:
    """High-rate inbound flood from many sources toward one target."""
    rng = _rng(spec)
    target = INTERNAL_HOSTS[0]
    flows: list[FlowRecord] = []
    for index in range(spec.count):
        flows.append(
            _flow(
                spec,
                offset=index * 0.005,
                src=f"203.0.{rng.randint(1, 254)}.{rng.randint(1, 254)}",
                dst=target,
                src_port=rng.randint(1024, 65535),
                dst_port=80,
                direction=Direction.INBOUND,
                service="http",
                state="S0",
                packets=rng.randint(1, 3),
                src_bytes=rng.randint(40, 120),
                dst_bytes=0,
                duration=0.0005,
                syn=1,
                ack=0,
                fin=0,
            )
        )
    return flows


def _brute_force(spec: GenerationSpec) -> list[FlowRecord]:
    """Repeated short SSH connections from one source, then a success."""
    rng = _rng(spec)
    src = rng.choice(EXTERNAL_HOSTS)
    target = INTERNAL_HOSTS[1]
    flows: list[FlowRecord] = []
    for index in range(spec.count):
        is_last = index == spec.count - 1
        flows.append(
            _flow(
                spec,
                offset=index * 1.5,
                src=src,
                dst=target,
                src_port=rng.randint(49152, 65535),
                dst_port=22,
                direction=Direction.INBOUND,
                service="ssh",
                state="SF" if is_last else "REJ",
                packets=rng.randint(4, 8),
                src_bytes=rng.randint(200, 400),
                dst_bytes=rng.randint(120, 300) if is_last else 0,
                duration=round(rng.uniform(0.1, 0.4), 3),
            )
        )
    return flows


def _beaconing(spec: GenerationSpec) -> list[FlowRecord]:
    """Periodic outbound C2 check-in at a near-constant interval.

    The detectable property is collapsed inter-arrival jitter, not volume: each
    beacon is small and would be invisible to a byte-threshold rule.
    """
    rng = _rng(spec)
    src = INTERNAL_HOSTS[2]
    dst = EXTERNAL_HOSTS[0]
    interval = 60.0
    flows: list[FlowRecord] = []
    for index in range(spec.count):
        # Jitter is deliberately tiny — that is the signal. It is always a
        # positive delay so no record ever precedes spec.start.
        flows.append(
            _flow(
                spec,
                offset=index * interval + rng.uniform(0.0, 0.3),
                src=src,
                dst=dst,
                src_port=rng.randint(49152, 65535),
                dst_port=443,
                direction=Direction.OUTBOUND,
                service="https",
                packets=rng.randint(4, 6),
                src_bytes=rng.randint(180, 240),
                dst_bytes=rng.randint(120, 200),
                duration=round(rng.uniform(0.08, 0.2), 3),
            )
        )
    return flows


def _exfiltration(spec: GenerationSpec) -> list[FlowRecord]:
    """Large sustained outbound transfers with extreme byte asymmetry."""
    rng = _rng(spec)
    src = INTERNAL_HOSTS[3]
    dst = EXTERNAL_HOSTS[2]
    flows: list[FlowRecord] = []
    for index in range(spec.count):
        flows.append(
            _flow(
                spec,
                offset=index * rng.uniform(20.0, 45.0),
                src=src,
                dst=dst,
                src_port=rng.randint(49152, 65535),
                dst_port=443,
                direction=Direction.OUTBOUND,
                service="https",
                packets=rng.randint(400, 1200),
                src_bytes=rng.randint(2_000_000, 8_000_000),
                dst_bytes=rng.randint(500, 2000),
                duration=round(rng.uniform(30.0, 120.0), 3),
            )
        )
    return flows


def _insider_threat(spec: GenerationSpec) -> list[FlowRecord]:
    """Off-hours access by an authenticated employee to systems they rarely touch.

    Deliberately **benign in shape**: well-formed sessions on expected ports with
    ordinary byte counts. T5 is a log-derived family
    ([prd.md](../../prd.md) §threat families), so the flow side alone must not be
    enough to flag it — that is what makes the late-fusion model necessary and
    what makes a flow-only baseline measurably worse on this label.
    """
    rng = _rng(spec)
    src = rng.choice(INTERNAL_HOSTS)
    flows: list[FlowRecord] = []
    for index in range(spec.count):
        flows.append(
            _flow(
                spec,
                offset=OFF_HOURS.total_seconds() + index * rng.uniform(20.0, 90.0),
                src=src,
                dst=rng.choice(INSIDER_TARGETS),
                src_port=rng.randint(49152, 65535),
                dst_port=rng.choice((443, 5432, 22)),
                service="https",
                state="SF",
                packets=rng.randint(12, 60),
                src_bytes=rng.randint(600, 4000),
                dst_bytes=rng.randint(2000, 90000),
                duration=round(rng.uniform(0.4, 12.0), 3),
                syn=1,
                ack=rng.randint(8, 40),
                rst=0,
                fin=1,
            )
        )
    return flows


_BUILDERS = {
    Scenario.NORMAL: _normal,
    Scenario.PORT_SCAN: _port_scan,
    Scenario.DDOS: _ddos,
    Scenario.BRUTE_FORCE: _brute_force,
    Scenario.BEACONING: _beaconing,
    Scenario.EXFILTRATION: _exfiltration,
    Scenario.INSIDER_THREAT: _insider_threat,
}


def generate_flows(spec: GenerationSpec) -> list[FlowRecord]:
    """Generate flow records for one scenario.

    Deterministic: identical specs always yield identical records (R-42).
    """
    return _BUILDERS[spec.scenario](spec)


def _brute_force_logs(spec: GenerationSpec) -> list[LogRecord]:
    """Repeated authentication failures, ending in one success (T4)."""
    user = "j.rivera"
    host = INTERNAL_HOSTS[1]
    logs: list[LogRecord] = []
    for index in range(spec.count):
        succeeded = index == spec.count - 1
        verb = "Accepted" if succeeded else "Failed"
        logs.append(
            LogRecord(
                timestamp=spec.start + timedelta(seconds=index * 1.5),
                host=host,
                service="sshd",
                level=LogLevel.INFO if succeeded else LogLevel.WARNING,
                message=f"{verb} password for {user} from {EXTERNAL_HOSTS[1]} port 51234 ssh2",
                parameters={"user": user, "source_ip": EXTERNAL_HOSTS[1]},
                label=LABELS[spec.scenario],
            )
        )
    return logs


def _insider_threat_logs(spec: GenerationSpec) -> list[LogRecord]:
    """New privilege use and an unusual file/API sequence, off-hours (T5).

    All three signatures prd.md names for T5 appear here — off-hours access, new
    privilege use, unusual file/API sequences — because this label is only
    detectable from logs.
    """
    user = "j.rivera"
    host = INTERNAL_HOSTS[1]
    target = INSIDER_TARGETS[0]
    events: tuple[tuple[str, LogLevel, str, dict[str, str]], ...] = (
        (
            "sshd",
            LogLevel.INFO,
            f"Accepted publickey for {user} from {INTERNAL_HOSTS[0]} port 52110 ssh2",
            {"user": user},
        ),
        (
            "sudo",
            LogLevel.WARNING,
            f"sudo:  {user} : TTY=pts/0 ; PWD=/home/{user} ; USER=root ; "
            "COMMAND=/usr/bin/cat /srv/finance/payroll.csv",
            {"user": user, "target_user": "root"},
        ),
        (
            "sudo",
            LogLevel.WARNING,
            f"pam_unix(sudo:session): session opened for user root(uid=0) by {user}(uid=1001)",
            {"user": user, "target_user": "root"},
        ),
        (
            "auditd",
            LogLevel.WARNING,
            f"file.read path=/srv/finance/payroll.csv host={target} bytes=884312",
            {"user": user, "path": "/srv/finance/payroll.csv"},
        ),
        (
            "api-gateway",
            LogLevel.ERROR,
            f"bulk access: {user} requested GET /v1/employees/salaries 412 times in 6m",
            {"user": user, "endpoint": "/v1/employees/salaries"},
        ),
    )
    logs: list[LogRecord] = []
    for index in range(spec.count):
        service, level, message, parameters = events[index % len(events)]
        logs.append(
            LogRecord(
                timestamp=spec.start + OFF_HOURS + timedelta(seconds=index * 45.0),
                host=host,
                service=service,
                level=level,
                message=message,
                parameters=parameters,
                label=LABELS[spec.scenario],
            )
        )
    return logs


#: Scenarios that produce log records. A scenario absent from this table has no
#: log-side signature, and asking for its logs raises rather than returning an
#: empty list, which would read as "no anomalies" (R-06).
_LOG_BUILDERS: dict[Scenario, Callable[[GenerationSpec], list[LogRecord]]] = {
    Scenario.BRUTE_FORCE: _brute_force_logs,
    Scenario.INSIDER_THREAT: _insider_threat_logs,
}


#: Scenarios that produce log records. Public so callers can branch without
#: importing the private builder table.
LOG_SCENARIOS: frozenset[Scenario] = frozenset(_LOG_BUILDERS)


def generate_logs(spec: GenerationSpec) -> list[LogRecord]:
    """Generate log records for one scenario.

    Raises:
        ValueError: if the scenario has no log-side signature (R-06).
    """
    builder = _LOG_BUILDERS.get(spec.scenario)
    if builder is None:
        supported = ", ".join(sorted(scenario.value for scenario in _LOG_BUILDERS))
        raise ValueError(f"log records are only defined for {supported}, got {spec.scenario.value}")
    return builder(spec)


@dataclass(frozen=True, slots=True)
class SyntheticDataset:
    """A labelled collection of generated telemetry."""

    flows: tuple[FlowRecord, ...]
    logs: tuple[LogRecord, ...]

    def __len__(self) -> int:
        """Total record count across both modalities."""
        return len(self.flows) + len(self.logs)

    def label_counts(self) -> dict[str, int]:
        """Return how many records carry each label, for imbalance reporting."""
        counts: dict[str, int] = {}
        # Annotated so mypy keeps the union instead of widening to BaseModel.
        records: tuple[FlowRecord | LogRecord, ...] = (*self.flows, *self.logs)
        for record in records:
            key = record.label or "unlabelled"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))


def generate_dataset(
    per_scenario: int,
    seed: int,
    scenarios: tuple[Scenario, ...] = tuple(Scenario),
) -> SyntheticDataset:
    """Generate a balanced dataset across every requested scenario.

    Each scenario gets its own derived seed so that adding a scenario to the list
    does not change the records produced for the others.
    """
    if not scenarios:
        raise ValueError("at least one scenario is required")
    if per_scenario <= 0:
        raise ValueError(f"per_scenario must be positive, got {per_scenario}")

    flows: list[FlowRecord] = []
    logs: list[LogRecord] = []
    for index, scenario in enumerate(scenarios):
        spec = GenerationSpec(scenario=scenario, count=per_scenario, seed=seed + index)
        flows.extend(generate_flows(spec))
        if scenario in _LOG_BUILDERS:
            logs.extend(generate_logs(spec))

    return SyntheticDataset(flows=tuple(flows), logs=tuple(logs))
