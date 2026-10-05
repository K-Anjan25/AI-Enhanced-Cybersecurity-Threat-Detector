"""Parsers for the public benchmark datasets (T-103).

Both UNSW-NB15 and CIC-IDS2017 are turned into the same ``flow@1`` records the
synthetic generator emits, so everything downstream — features, windows,
splits, baselines — is dataset-agnostic.

Three rules this module is strict about, because each one has already bitten
someone:

* **Nothing is dropped silently.** A row that cannot be represented in
  ``flow@1`` is counted against a named reason in the report, and columns the
  mapping does not consume are listed rather than discarded without a word.
  ``ParseReport.raise_for_empty`` turns a parse that produced nothing into an
  error instead of an empty dataset that trains a model on air.
* **The monitored network is a property of the capture, not of the record.**
  ``Direction`` is defined relative to a boundary, so each dataset declares its
  own. Guessing from RFC 1918 addresses would classify 99.2 % of UNSW-NB15 as
  external-to-external, which is not a direction.
* **Unknown means unknown.** A protocol outside the three the pipeline models
  is a rejected row, not a coerced one; a ``service`` of ``-`` is ``None``, not
  the string ``"-"``.

Deviations from the published schemas are recorded per dataset in
``aegis_ml.data.datasets`` and repeated where the parser handles them.
"""

from __future__ import annotations

import csv
import ipaddress
import os
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aegis_ml.data.datasets import UNSW_ATTACK_CAT_CODES, DatasetId
from aegis_ml.data.records import SCHEMA_VERSION_FLOW, Direction, FlowRecord, Protocol

#: The network each capture was taken from, as CIDR ranges. ``direction`` is
#: measured against this. CIC-IDS2017's ranges are the victim and attacker
#: networks UNB publishes on the dataset page; UNSW-NB15 was captured on the
#: ADFA campus, whose address space is 149.171.0.0/16.
MONITORED_NETWORKS: Final[dict[DatasetId, tuple[str, ...]]] = {
    "unsw-nb15": ("149.171.0.0/16",),
    "cic-ids2017": ("192.168.10.0/24", "172.16.0.0/12", "205.174.165.0/24"),
}

#: Well-known ports used to fill ``service`` when the source has no such column.
WELL_KNOWN_PORTS: Final[dict[int, str]] = {
    20: "ftp-data",
    21: "ftp",
    22: "ssh",
    23: "telnet",
    25: "smtp",
    53: "dns",
    80: "http",
    110: "pop3",
    143: "imap",
    443: "https",
    3389: "rdp",
}

#: CIC-IDS2017 numbers its protocols; ``flow@1`` names them.
CIC_PROTOCOL_NUMBERS: Final[dict[int, Protocol]] = {
    1: Protocol.ICMP,
    6: Protocol.TCP,
    17: Protocol.UDP,
}

#: UNSW-NB15 names its protocols, but 57 distinct values appear in a 10,000-row
#: sample. Only these three are modelled.
UNSW_PROTOCOL_NAMES: Final[dict[str, Protocol]] = {
    "tcp": Protocol.TCP,
    "udp": Protocol.UDP,
    "icmp": Protocol.ICMP,
}

#: Timestamp formats tried in order. CIC-IDS2017 publishes seconds and an
#: AM/PM suffix; the reachable mirror truncates both away.
_CIC_TIMESTAMP_FORMATS: Final[tuple[str, ...]] = (
    "%m/%d/%Y %H:%M:%S %p",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %H:%M",
)

#: Neither dataset states a timezone. Records are stamped UTC and every
#: timestamp therefore carries a constant unknown offset, which cannot affect a
#: temporal split (all rows shift together) but does mean absolute times in
#: ``flow@1`` are not wall-clock truth.
_ASSUMED_TZ = UTC

#: UNSW-NB15 marks "no value" with a dash.
_UNSW_NULL = "-"


class ParseReport(BaseModel):
    """What a parse did, including everything it could not do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_file: str
    dataset_id: DatasetId
    rows_read: int = Field(ge=0)
    parsed: int = Field(ge=0)
    rejected: int = Field(ge=0)
    rejection_reasons: Mapping[str, int] = Field(default_factory=dict)
    unmapped_columns: tuple[str, ...] = ()

    def raise_for_empty(self) -> None:
        """Fail loudly when a parse produced no usable records at all.

        An empty dataset is worse than an error: it trains a model, reports
        metrics, and only fails when someone tries to act on the result.
        """
        if self.parsed:
            return
        reasons = ", ".join(f"{k}={v}" for k, v in sorted(self.rejection_reasons.items()))
        msg = f"{self.source_file}: parsed 0 of {self.rows_read} rows ({reasons or 'no rows read'})"
        raise ValueError(msg)


class ParsedDataset(BaseModel):
    """Parsed records plus the report describing how they were obtained."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    records: tuple[FlowRecord, ...]
    report: ParseReport


class _RowError(Exception):
    """Raised internally to reject one row for a named reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _direction(
    src: ipaddress.IPv4Address,
    dst: ipaddress.IPv4Address,
    networks: Sequence[ipaddress.IPv4Network],
) -> Direction:
    """Classify a flow relative to the monitored network."""
    src_in = any(src in n for n in networks)
    dst_in = any(dst in n for n in networks)
    if src_in and dst_in:
        return Direction.INTERNAL
    if src_in:
        return Direction.OUTBOUND
    if dst_in:
        return Direction.INBOUND
    raise _RowError("outside_monitored_network")


def _parse_networks(cidrs: Iterable[str]) -> list[ipaddress.IPv4Network]:
    networks: list[ipaddress.IPv4Network] = []
    for cidr in cidrs:
        network = ipaddress.ip_network(cidr)
        if not isinstance(network, ipaddress.IPv4Network):
            msg = f"monitored network {cidr!r} is not an IPv4 range"
            raise ValueError(msg)
        networks.append(network)
    return networks


def _int(value: str, field: str) -> int:
    try:
        return int(float(value))
    except ValueError as exc:
        raise _RowError(f"bad_int:{field}") from exc


def _float(value: str, field: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise _RowError(f"bad_float:{field}") from exc


def _port(value: str) -> int:
    port = _int(value, "port")
    if not 0 <= port <= 65535:
        raise _RowError("port_out_of_range")
    return port


def _ip(value: str, field: str) -> ipaddress.IPv4Address:
    try:
        return ipaddress.IPv4Address(value)
    except ValueError as exc:
        raise _RowError(f"bad_ip:{field}") from exc


def _unsw_timestamp(value: str) -> datetime:
    """Parse UNSW ``stime``.

    The published CSV uses ``17/02/2015 08:40:10 PM``; the reachable mirror
    stores Unix epoch seconds instead. Both are accepted, because silently
    reading one as the other would place every record in 1970 or reject it.
    """
    text = value.strip()
    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=_ASSUMED_TZ)
    for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=_ASSUMED_TZ)
        except ValueError:
            continue
    raise _RowError("bad_timestamp:stime")


def _cic_timestamp(value: str) -> datetime:
    """Parse CIC-IDS2017 ``Timestamp``, with or without seconds and AM/PM."""
    text = value.strip()
    for fmt in _CIC_TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=_ASSUMED_TZ)
        except ValueError:
            continue
    raise _RowError("bad_timestamp:Timestamp")


def _unsw_label(row: Mapping[str, str]) -> str:
    """Map UNSW ``attack_cat`` to a ``flow@1`` label.

    The published dataset uses category names; the reachable mirror uses the
    integer codes in ``UNSW_ATTACK_CAT_CODES``. Both are accepted.
    """
    raw = row["attack_cat"].strip()
    if raw in ("", _UNSW_NULL):
        return "normal"
    if raw.isdigit():
        code = int(raw)
        name = UNSW_ATTACK_CAT_CODES.get(code)
        if name is None:
            raise _RowError(f"unknown_attack_cat_code:{code}")
        return name
    return raw


def _service_from_port(port: int) -> str | None:
    return WELL_KNOWN_PORTS.get(port)


def _collect(
    rows: Iterable[Mapping[str, str]],
    build: Callable[[Mapping[str, str]], FlowRecord],
    *,
    dataset_id: DatasetId,
    source_file: str,
    consumed: frozenset[str],
) -> ParsedDataset:
    """Run one row-builder over a CSV, accumulating records and rejections."""
    records: list[FlowRecord] = []
    reasons: Counter[str] = Counter()
    read = 0
    columns: set[str] = set()

    for row in rows:
        read += 1
        columns.update(row)
        try:
            records.append(build(row))
        except _RowError as exc:
            reasons[exc.reason] += 1
        except ValidationError as exc:
            # A row that satisfies the parser but not flow@1 is still a
            # rejection with a reason, never a crash that loses the whole file.
            reasons[f"schema:{exc.errors()[0]['type']}"] += 1

    unmapped = tuple(sorted(c for c in columns if c.strip() and c.strip() not in consumed))
    report = ParseReport(
        source_file=source_file,
        dataset_id=dataset_id,
        rows_read=read,
        parsed=len(records),
        rejected=sum(reasons.values()),
        rejection_reasons=dict(sorted(reasons.items())),
        unmapped_columns=unmapped,
    )
    return ParsedDataset(records=tuple(records), report=report)


# Columns each parser actually reads. Anything else in the file is reported as
# unmapped rather than quietly ignored.
_UNSW_CONSUMED: Final[frozenset[str]] = frozenset(
    {
        "srcip",
        "sport",
        "dstip",
        "dsport",
        "proto",
        "state",
        "service",
        "dur",
        "sbytes",
        "dbytes",
        "spkts",
        "dpkts",
        "stime",
        "attack_cat",
        "label",
    }
)
_CIC_CONSUMED: Final[frozenset[str]] = frozenset(
    {
        "Source IP",
        "Source Port",
        "Destination IP",
        "Destination Port",
        "Protocol",
        "Timestamp",
        "Flow Duration",
        "Total Fwd Packets",
        "Total Backward Packets",
        "Total Length of Fwd Packets",
        "Total Length of Bwd Packets",
        "FIN Flag Count",
        "SYN Flag Count",
        "RST Flag Count",
        "PSH Flag Count",
        "ACK Flag Count",
        "URG Flag Count",
        "Label",
    }
)


def _read_csv(path: str) -> Iterable[Mapping[str, str]]:
    """Yield rows with whitespace stripped from keys *and* values.

    CIC-IDS2017's header carries a leading space on most columns and some rows
    carry spaces around values; both would otherwise become part of the data.
    """
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            yield {(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}


def parse_unsw_nb15(path: str, *, monitored: Sequence[str] | None = None) -> ParsedDataset:
    """Parse a UNSW-NB15 CSV into ``flow@1`` records.

    Args:
        path: CSV file to read.
        monitored: CIDR ranges of the monitored network. Defaults to the ADFA
            campus range the dataset was captured on.
    """
    networks = _parse_networks(monitored or MONITORED_NETWORKS["unsw-nb15"])

    def build(row: Mapping[str, str]) -> FlowRecord:
        proto = UNSW_PROTOCOL_NAMES.get(row["proto"].lower())
        if proto is None:
            raise _RowError(f"unsupported_protocol:{row['proto']}")
        src_ip = _ip(row["srcip"], "srcip")
        dst_ip = _ip(row["dstip"], "dstip")
        dst_port = _port(row["dsport"])
        service = row["service"]
        return FlowRecord(
            schema_version=SCHEMA_VERSION_FLOW,
            timestamp=_unsw_timestamp(row["stime"]),
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=_port(row["sport"]),
            dst_port=dst_port,
            protocol=proto,
            direction=_direction(src_ip, dst_ip, networks),
            # '-' is UNSW's null marker, not a service name.
            service=None if service in ("", _UNSW_NULL) else service.lower(),
            state=None if row["state"] in ("", _UNSW_NULL) else row["state"].upper(),
            packets=_int(row["spkts"], "spkts") + _int(row["dpkts"], "dpkts"),
            src_packets=_int(row["spkts"], "spkts"),
            dst_packets=_int(row["dpkts"], "dpkts"),
            src_bytes=_int(row["sbytes"], "sbytes"),
            dst_bytes=_int(row["dbytes"], "dbytes"),
            # dur is already seconds here; values as small as 2e-06 appear.
            duration=_float(row["dur"], "dur"),
            label=_unsw_label(row),
        )

    return _collect(
        _read_csv(path),
        build,
        dataset_id="unsw-nb15",
        source_file=os.path.basename(path),
        consumed=_UNSW_CONSUMED,
    )


def parse_cic_ids2017(path: str, *, monitored: Sequence[str] | None = None) -> ParsedDataset:
    """Parse a CIC-IDS2017 CSV into ``flow@1`` records.

    Args:
        path: CSV file to read.
        monitored: CIDR ranges of the monitored network. Defaults to the victim
            and attacker networks UNB publishes for this capture.
    """
    networks = _parse_networks(monitored or MONITORED_NETWORKS["cic-ids2017"])

    def build(row: Mapping[str, str]) -> FlowRecord:
        number = _int(row["Protocol"], "Protocol")
        proto = CIC_PROTOCOL_NUMBERS.get(number)
        if proto is None:
            raise _RowError(f"unsupported_protocol:{number}")
        src_ip = _ip(row["Source IP"], "Source IP")
        dst_ip = _ip(row["Destination IP"], "Destination IP")
        dst_port = _port(row["Destination Port"])
        label = row["Label"]
        return FlowRecord(
            schema_version=SCHEMA_VERSION_FLOW,
            timestamp=_cic_timestamp(row["Timestamp"]),
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=_port(row["Source Port"]),
            dst_port=dst_port,
            protocol=proto,
            direction=_direction(src_ip, dst_ip, networks),
            # This cut of CICFlowMeter carries no service column.
            service=_service_from_port(dst_port),
            state=None,
            packets=_int(row["Total Fwd Packets"], "Total Fwd Packets")
            + _int(row["Total Backward Packets"], "Total Backward Packets"),
            src_packets=_int(row["Total Fwd Packets"], "Total Fwd Packets"),
            dst_packets=_int(row["Total Backward Packets"], "Total Backward Packets"),
            src_bytes=_int(row["Total Length of Fwd Packets"], "Total Length of Fwd Packets"),
            dst_bytes=_int(row["Total Length of Bwd Packets"], "Total Length of Bwd Packets"),
            # Flow Duration is in microseconds; flow@1 stores seconds.
            duration=_float(row["Flow Duration"], "Flow Duration") / 1_000_000.0,
            syn=_int(row["SYN Flag Count"], "SYN Flag Count"),
            ack=_int(row["ACK Flag Count"], "ACK Flag Count"),
            rst=_int(row["RST Flag Count"], "RST Flag Count"),
            fin=_int(row["FIN Flag Count"], "FIN Flag Count"),
            psh=_int(row["PSH Flag Count"], "PSH Flag Count"),
            urg=_int(row["URG Flag Count"], "URG Flag Count"),
            label="normal" if label.upper() == "BENIGN" else label,
        )

    return _collect(
        _read_csv(path),
        build,
        dataset_id="cic-ids2017",
        source_file=os.path.basename(path),
        consumed=_CIC_CONSUMED,
    )


def write_ndjson(records: Sequence[FlowRecord], path: str) -> int:
    """Serialise records as newline-delimited JSON. Returns the count written.

    NDJSON rather than the Parquet that task.md T-103 names: the project has no
    dataframe or columnar dependency yet, and NDJSON is already the storage
    format the synthetic generator and the ingest path use. One record per line
    also streams, which 2.5 M rows require.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json())
            handle.write("\n")
    return len(records)
