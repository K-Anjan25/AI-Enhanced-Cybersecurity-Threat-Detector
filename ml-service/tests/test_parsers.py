"""Tests for the benchmark dataset parsers (T-103).

The fixtures are real rows copied verbatim out of the fetched datasets, not
invented ones: ``cic_ids2017_sample.csv`` is 12 BENIGN and 12 DDoS flows from
the Friday capture, ``unsw_nb15_sample.csv`` is 8 normal and 8 attack flows
carrying the official 49-column schema. Expected values below were read out of
those files by hand, so a change to the mapping breaks a test rather than
silently changing what a record means.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest
from aegis_ml.data.parsers import (
    MONITORED_NETWORKS,
    parse_cic_ids2017,
    parse_unsw_nb15,
    write_ndjson,
)
from aegis_ml.data.records import Direction, FlowRecord, Protocol

FIXTURES = Path(__file__).parent / "fixtures"
CIC_FIXTURE = FIXTURES / "cic_ids2017_sample.csv"
UNSW_FIXTURE = FIXTURES / "unsw_nb15_sample.csv"


def test_cic_parses_every_row_of_the_fixture() -> None:
    result = parse_cic_ids2017(str(CIC_FIXTURE))
    assert result.report.rows_read == 24
    assert result.report.parsed == 24
    assert result.report.rejected == 0
    assert result.report.rejection_reasons == {}


def test_cic_first_record_matches_the_file_by_hand() -> None:
    """Row one of the fixture, field by field.

    ``104.16.207.165,443,192.168.10.5,54865,6,07/07/2017 03:30,3,2,0,12,0,...``
    """
    record = parse_cic_ids2017(str(CIC_FIXTURE)).records[0]
    assert str(record.src_ip) == "104.16.207.165"
    assert record.src_port == 443
    assert str(record.dst_ip) == "192.168.10.5"
    assert record.dst_port == 54865
    assert record.protocol is Protocol.TCP
    assert record.timestamp == datetime(2017, 7, 7, 3, 30, tzinfo=UTC)
    assert record.src_packets == 2
    assert record.dst_packets == 0
    assert record.packets == 2
    assert record.src_bytes == 12
    assert record.dst_bytes == 0
    assert record.ack == 1
    assert record.syn == 0
    assert record.label == "normal"


def test_cic_duration_is_converted_from_microseconds() -> None:
    """The file stores 3; flow@1 stores seconds, so this must be 3e-06."""
    record = parse_cic_ids2017(str(CIC_FIXTURE)).records[0]
    assert record.duration == pytest.approx(3e-06)


def test_cic_strips_the_leading_space_off_column_names() -> None:
    """CIC-IDS2017's header is ' Source IP'. An unstripped lookup raises."""
    with CIC_FIXTURE.open(newline="", encoding="utf-8-sig") as handle:
        header = next(csv.reader(handle))
    assert header[0] == " Source IP"
    assert header[0] != header[0].strip()
    # Parsing succeeds only because the keys are stripped on the way in.
    assert parse_cic_ids2017(str(CIC_FIXTURE)).report.parsed == 24


def test_cic_reports_unmapped_columns_instead_of_dropping_them() -> None:
    report = parse_cic_ids2017(str(CIC_FIXTURE)).report
    assert "Flow Bytes/s" in report.unmapped_columns
    assert "Min Packet Length" in report.unmapped_columns
    # Consumed columns must not be reported as unmapped.
    assert "Source IP" not in report.unmapped_columns
    assert "Label" not in report.unmapped_columns


def test_cic_direction_comes_from_the_monitored_network() -> None:
    """A public source and a 192.168.10.x destination is inbound, not internal."""
    record = parse_cic_ids2017(str(CIC_FIXTURE)).records[0]
    assert record.direction is Direction.INBOUND


def test_cic_direction_changes_with_the_declared_boundary() -> None:
    """Direction is a property of the capture, so a different boundary differs."""
    path = str(CIC_FIXTURE)
    default = parse_cic_ids2017(path).records[0].direction
    everything = parse_cic_ids2017(path, monitored=["0.0.0.0/0"]).records[0].direction
    assert default is Direction.INBOUND
    assert everything is Direction.INTERNAL


def test_cic_attack_label_is_preserved_and_benign_becomes_normal() -> None:
    labels = {record.label for record in parse_cic_ids2017(str(CIC_FIXTURE)).records}
    assert labels == {"normal", "DDoS"}


def test_unsw_parses_every_row_it_can_and_accounts_for_the_one_it_cannot() -> None:
    """16 rows in, 15 out: one real row carries proto 'ipnip', which is not modelled.

    The rejection is asserted rather than tolerated, so a future widening of the
    protocol table shows up as a change to this test rather than as a silent
    shift in how many records the pipeline sees.
    """
    report = parse_unsw_nb15(str(UNSW_FIXTURE)).report
    assert report.rows_read == 16
    assert report.parsed == 15
    assert report.rejected == 1
    assert report.rejection_reasons == {"unsupported_protocol:ipnip": 1}


def test_unsw_first_record_matches_the_file_by_hand() -> None:
    """Row one: ``149.171.126.18,47439,175.45.176.1,53,udp,INT,2e-06,264,0,...``."""
    record = parse_unsw_nb15(str(UNSW_FIXTURE)).records[0]
    assert str(record.src_ip) == "149.171.126.18"
    assert record.src_port == 47439
    assert str(record.dst_ip) == "175.45.176.1"
    assert record.dst_port == 53
    assert record.protocol is Protocol.UDP
    assert record.service == "dns"
    assert record.state == "INT"
    assert record.duration == pytest.approx(2e-06)
    assert record.src_packets == 2
    assert record.dst_packets == 0
    assert record.src_bytes == 264
    assert record.dst_bytes == 0
    assert record.label == "normal"


def test_unsw_epoch_timestamp_is_decoded() -> None:
    """The reachable mirror stores ``stime`` as Unix seconds: 1421932424."""
    record = parse_unsw_nb15(str(UNSW_FIXTURE)).records[0]
    assert record.timestamp == datetime(2015, 1, 22, 13, 13, 44, tzinfo=UTC)


def test_unsw_attack_cat_code_is_mapped_to_its_category_name() -> None:
    """attack_cat '4' is Generic in the mirror's own code table."""
    attack = [r for r in parse_unsw_nb15(str(UNSW_FIXTURE)).records if r.label != "normal"]
    assert attack
    assert attack[0].label == "Generic"


def test_unsw_dash_service_becomes_none_not_the_string_dash() -> None:
    """'-' is UNSW's null marker; storing it as a service name would be a lie."""
    result = parse_unsw_nb15(str(UNSW_FIXTURE))
    assert any(r.service is None for r in result.records)
    assert all(r.service != "-" for r in result.records)


def test_unsw_reports_unmapped_columns() -> None:
    report = parse_unsw_nb15(str(UNSW_FIXTURE)).report
    assert "ct_srv_src" in report.unmapped_columns
    assert "ltime" in report.unmapped_columns
    assert "srcip" not in report.unmapped_columns


def test_unsupported_protocol_is_counted_not_coerced(tmp_path: Path) -> None:
    """57 protocol names appear in UNSW-NB15; only three are modelled."""
    target = tmp_path / "unsw.csv"
    rows = _rewrite(UNSW_FIXTURE, target, {"proto": "ospf"})
    assert rows == 16
    report = parse_unsw_nb15(str(target)).report
    assert report.parsed == 0
    assert report.rejected == 16
    assert report.rejection_reasons == {"unsupported_protocol:ospf": 16}


def test_row_violating_the_flow_contract_is_counted_not_fatal(tmp_path: Path) -> None:
    """A negative duration fails flow@1's own validation; the parse must survive."""
    target = tmp_path / "cic.csv"
    _rewrite(CIC_FIXTURE, target, {" Flow Duration": "-5"})
    report = parse_cic_ids2017(str(target)).report
    assert report.rejected == 24
    assert report.parsed == 0
    assert set(report.rejection_reasons) == {"schema:greater_than_equal"}


def test_bad_ip_is_counted_with_a_named_reason(tmp_path: Path) -> None:
    target = tmp_path / "cic.csv"
    _rewrite(CIC_FIXTURE, target, {" Source IP": "not-an-address"})
    report = parse_cic_ids2017(str(target)).report
    assert report.rejection_reasons == {"bad_ip:Source IP": 24}


def test_raise_for_empty_names_the_reasons(tmp_path: Path) -> None:
    target = tmp_path / "unsw.csv"
    _rewrite(UNSW_FIXTURE, target, {"proto": "ospf"})
    result = parse_unsw_nb15(str(target))
    with pytest.raises(ValueError, match="unsupported_protocol:ospf=16"):
        result.report.raise_for_empty()


def test_raise_for_empty_passes_when_something_parsed() -> None:
    parse_cic_ids2017(str(CIC_FIXTURE)).report.raise_for_empty()


def test_monitored_networks_are_ipv4_and_parse() -> None:
    assert MONITORED_NETWORKS["unsw-nb15"] == ("149.171.0.0/16",)
    assert "192.168.10.0/24" in MONITORED_NETWORKS["cic-ids2017"]


def test_non_ipv4_monitored_network_is_refused() -> None:
    with pytest.raises(ValueError, match="not an IPv4 range"):
        parse_cic_ids2017(str(CIC_FIXTURE), monitored=["2001:db8::/32"])


def test_write_ndjson_round_trips_through_flow_record(tmp_path: Path) -> None:
    records = parse_cic_ids2017(str(CIC_FIXTURE)).records
    out = tmp_path / "flows.ndjson"
    assert write_ndjson(records, str(out)) == len(records)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(records)
    restored = [FlowRecord.model_validate_json(line) for line in lines]
    assert restored == list(records)


def _rewrite(source: Path, target: Path, overrides: dict[str, str]) -> int:
    """Copy a fixture, forcing some columns to fixed values. Returns the row count."""
    with source.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            row.update(overrides)
            writer.writerow(row)
    return len(rows)
