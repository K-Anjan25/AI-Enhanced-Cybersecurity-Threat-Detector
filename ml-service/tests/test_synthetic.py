"""Tests for the deterministic synthetic generator (T-106, R-42)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aegis_ml.data.records import Direction, LogLevel
from aegis_ml.data.synthetic import (
    EPOCH,
    LABELS,
    GenerationSpec,
    Scenario,
    generate_dataset,
    generate_flows,
    generate_logs,
)


def spec(scenario: Scenario, count: int = 25, seed: int = 7) -> GenerationSpec:
    return GenerationSpec(scenario=scenario, count=count, seed=seed)


def test_same_seed_produces_byte_identical_output() -> None:
    """R-42: the generator must be reproducible or tests cannot rely on it."""
    first = [record.model_dump_json() for record in generate_flows(spec(Scenario.PORT_SCAN))]
    second = [record.model_dump_json() for record in generate_flows(spec(Scenario.PORT_SCAN))]

    assert first == second
    assert len(first) == 25


def test_different_seeds_produce_different_output() -> None:
    """Determinism must not collapse into a constant output."""
    a = [r.model_dump_json() for r in generate_flows(spec(Scenario.NORMAL, seed=1))]
    b = [r.model_dump_json() for r in generate_flows(spec(Scenario.NORMAL, seed=2))]

    assert a != b


def test_repeated_calls_do_not_advance_shared_random_state() -> None:
    """Interleaving generations must not perturb each other."""
    before = [r.model_dump_json() for r in generate_flows(spec(Scenario.DDOS))]
    generate_flows(spec(Scenario.NORMAL, seed=99))
    after = [r.model_dump_json() for r in generate_flows(spec(Scenario.DDOS))]

    assert before == after


def test_every_scenario_yields_the_requested_count_and_label() -> None:
    for scenario in Scenario:
        flows = generate_flows(spec(scenario, count=10))

        assert len(flows) == 10, scenario
        assert {record.label for record in flows} == {LABELS[scenario]}, scenario


def test_generated_timestamps_start_at_the_fixed_epoch() -> None:
    """No record may depend on the wall clock (NFR-10 discipline)."""
    flows = generate_flows(spec(Scenario.BEACONING))

    assert flows[0].timestamp >= EPOCH
    assert flows[0].timestamp.tzinfo is UTC


def test_port_scan_sweeps_many_ports_from_one_source() -> None:
    """This is the feature the model is meant to pick up on (T1)."""
    flows = generate_flows(spec(Scenario.PORT_SCAN, count=50))

    sources = {record.src_ip for record in flows}
    ports = {record.dst_port for record in flows}
    assert len(sources) == 1
    assert len(ports) == 50
    assert all(record.syn == 1 and record.dst_bytes == 0 for record in flows)


def test_beaconing_interval_jitter_is_small() -> None:
    """Beaconing is detectable by collapsed jitter, not by volume (T6)."""
    flows = generate_flows(spec(Scenario.BEACONING, count=20))
    gaps = [
        (flows[i + 1].timestamp - flows[i].timestamp).total_seconds() for i in range(len(flows) - 1)
    ]

    assert gaps, "expected multiple beacons"
    assert max(gaps) - min(gaps) < 1.0
    assert 55.0 < sum(gaps) / len(gaps) < 65.0


def test_beaconing_flows_are_small() -> None:
    """A byte-threshold rule must not be what catches these."""
    flows = generate_flows(spec(Scenario.BEACONING))

    assert all(record.src_bytes < 500 for record in flows)


def test_exfiltration_is_byte_asymmetric_and_outbound() -> None:
    flows = generate_flows(spec(Scenario.EXFILTRATION, count=10))

    assert all(record.direction is Direction.OUTBOUND for record in flows)
    assert all(record.src_bytes > record.dst_bytes * 100 for record in flows)


def test_ddos_is_high_rate_inbound() -> None:
    flows = generate_flows(spec(Scenario.DDOS, count=40))
    span = (flows[-1].timestamp - flows[0].timestamp).total_seconds()

    assert all(record.direction is Direction.INBOUND for record in flows)
    assert len({record.src_ip for record in flows}) > 5
    assert span < 1.0, "a flood compressed into under a second"


def test_brute_force_ends_in_a_success() -> None:
    """The transition from repeated failure to success is the signal (T4)."""
    flows = generate_flows(spec(Scenario.BRUTE_FORCE, count=10))

    assert [record.state for record in flows[:-1]] == ["REJ"] * 9
    assert flows[-1].state == "SF"


def test_logs_are_defined_only_for_scenarios_that_have_them() -> None:
    """Asking for logs a scenario does not have must fail loudly (R-06)."""
    logs = generate_logs(spec(Scenario.BRUTE_FORCE, count=6))
    assert len(logs) == 6
    assert "Failed password" in logs[0].message
    assert "Accepted password" in logs[-1].message

    with pytest.raises(ValueError, match="only defined for brute_force, insider_threat"):
        generate_logs(spec(Scenario.NORMAL))


def test_insider_threat_flows_look_benign_but_happen_off_hours() -> None:
    """T5 is log-derived: the flow shape alone must not be what flags it."""
    flows = generate_flows(spec(Scenario.INSIDER_THREAT, count=25))

    assert all(record.label == "InsiderThreat" for record in flows)
    assert {record.timestamp.hour for record in flows} <= {2, 3, 4}
    # Well-formed sessions on expected ports, ordinary volumes — nothing a
    # byte-threshold or port-entropy rule would raise on.
    assert all(record.state == "SF" and record.syn == 1 for record in flows)
    assert all(record.dst_port in (22, 443, 5432) for record in flows)
    assert all(record.src_bytes < 5000 for record in flows)
    assert len({record.dst_ip for record in flows}) <= 2


def test_insider_threat_logs_carry_the_three_t5_signatures() -> None:
    """Off-hours access, new privilege use, unusual file/API sequences (prd T5)."""
    logs = generate_logs(spec(Scenario.INSIDER_THREAT, count=10))
    joined = "\n".join(record.message for record in logs)

    assert {record.timestamp.hour for record in logs} <= {2, 3, 4}
    assert "USER=root" in joined, "new privilege use"
    assert "session opened for user root" in joined
    assert "/srv/finance/payroll.csv" in joined, "unusual file sequence"
    assert "/v1/employees/salaries" in joined, "unusual API sequence"
    assert {record.label for record in logs} == {"InsiderThreat"}
    assert any(record.level is LogLevel.ERROR for record in logs)


def test_dataset_is_balanced_across_scenarios() -> None:
    dataset = generate_dataset(per_scenario=10, seed=3)

    counts = dataset.label_counts()
    assert set(counts) == {LABELS[s] for s in Scenario}
    assert len(counts) == 7

    # Brute force and insider threat contribute flows *and* log lines.
    both_modalities = {"BruteForce", "InsiderThreat"}
    for label, count in counts.items():
        assert count == (20 if label in both_modalities else 10), label
    assert len(dataset) == 7 * 10 + 2 * 10


def test_adding_a_scenario_does_not_change_the_others() -> None:
    """Each scenario gets a derived seed, so datasets stay comparable."""
    alone = [r.model_dump_json() for r in generate_flows(GenerationSpec(Scenario.NORMAL, 10, 3))]
    combined = generate_dataset(per_scenario=10, seed=3, scenarios=(Scenario.NORMAL, Scenario.DDOS))
    normal = [r.model_dump_json() for r in combined.flows if r.label == "normal"]

    assert normal == alone


def test_specs_are_validated() -> None:
    with pytest.raises(ValueError, match="count must be positive"):
        GenerationSpec(scenario=Scenario.NORMAL, count=0, seed=1)

    with pytest.raises(ValueError, match="timezone-aware"):
        GenerationSpec(scenario=Scenario.NORMAL, count=5, seed=1, start=datetime(2026, 1, 5))


def test_generate_dataset_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="at least one scenario"):
        generate_dataset(per_scenario=5, seed=1, scenarios=())

    with pytest.raises(ValueError, match="per_scenario must be positive"):
        generate_dataset(per_scenario=0, seed=1)


def test_a_negative_offset_is_refused() -> None:
    """A scenario builder cannot emit records before the declared start."""
    from aegis_ml.data.synthetic import _flow

    with pytest.raises(ValueError, match="offset must be >= 0"):
        _flow(
            spec(Scenario.NORMAL),
            offset=-0.5,
            src="10.4.20.11",
            dst="10.4.20.12",
            src_port=51234,
            dst_port=443,
        )
