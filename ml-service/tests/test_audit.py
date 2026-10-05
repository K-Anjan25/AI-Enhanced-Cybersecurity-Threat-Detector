"""Tests for the leakage audit (T-111).

The task's named requirement is that the audit fails on a deliberately leaked
scaler; ``test_a_scaler_fit_outside_train_is_caught`` is that test. The rest
build bad splits by hand, because an audit that only checks splits produced by
``split_windows`` would prove nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from aegis_ml.data.audit import (
    AuditReport,
    Finding,
    LeakKind,
    audit_split,
    audit_trained,
    blocking_findings,
    check_label_leakage,
    check_scaler_leakage,
    check_scaler_statistics,
)
from aegis_ml.data.features import NUMERIC_FEATURES, FlowFeatures, extract_flow_window
from aegis_ml.data.preprocess import StandardScaler
from aegis_ml.data.records import Direction, FlowRecord, Protocol
from aegis_ml.data.splits import Split, split_windows
from aegis_ml.data.windowing import Window, window_flows

EPOCH = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)


def host_flows(host: str, start: datetime, count: int = 30) -> list[FlowRecord]:
    """Build ``count`` evenly spaced flows from one host."""
    return [
        FlowRecord(
            timestamp=start + timedelta(seconds=index),
            src_ip=host,
            dst_ip="10.4.20.90",
            src_port=51000 + index,
            dst_port=443,
            protocol=Protocol.TCP,
            direction=Direction.INTERNAL,
            packets=10,
            src_packets=5,
            dst_packets=5,
            src_bytes=1200,
            dst_bytes=3400,
            duration=0.4,
            label="normal",
        )
        for index in range(count)
    ]


def clean_split() -> Split[FlowRecord]:
    """A split with entity churn, so both leakage invariants are satisfiable.

    Six hosts in three time bands, two per band: 36 windows, cut in the gaps.
    """
    bands = (
        ("10.4.20.11", "10.4.20.12"),
        ("10.4.20.13", "10.4.20.14"),
        ("10.4.20.15", "10.4.20.16"),
    )
    flows: list[FlowRecord] = []
    for band, hosts in enumerate(bands):
        for host in hosts:
            flows.extend(host_flows(host, EPOCH + timedelta(seconds=band * 40)))
    flows.sort(key=lambda record: record.timestamp)
    return split_windows(window_flows(flows, size=5), test_fraction=1 / 3, valid_fraction=0.5)


def row(value: float, label: str) -> FlowFeatures:
    """A feature row where only ``src_bytes`` varies; everything else is constant."""
    numeric = tuple(value if name == "src_bytes" else 1.0 for name in NUMERIC_FEATURES)
    return FlowFeatures(
        schema_version="features@1",
        entity="10.4.20.11",
        timestamp=EPOCH,
        categorical=("tcp", "http", "SF", "internal"),
        numeric=numeric,
        label=label,
    )


# --- a clean split passes ------------------------------------------------


def test_a_clean_split_passes_every_check() -> None:
    split = clean_split()

    report = audit_split(split, fit_on=split.train)

    assert report.ok is True
    assert report.findings == ()
    assert report.kinds() == frozenset()
    report.raise_for_leaks()  # must not raise


def test_the_fixture_really_is_clean() -> None:
    """Guard against the test above passing because the fixture is empty."""
    split = clean_split()

    assert len(split.train) == 12 and len(split.valid) == 12 and len(split.test) == 12
    assert split.dropped == 0


# --- the named requirement: a leaked scaler ------------------------------


def test_a_scaler_fit_outside_train_is_caught() -> None:
    """Fitting normalisation on train plus validation must fail the audit."""
    split = clean_split()
    leaked = (*split.train, *split.valid)

    findings = check_scaler_leakage(leaked, split)

    assert [finding.kind for finding in findings] == [LeakKind.SCALER]
    assert findings[0].value == 12.0
    assert "outside the training fold" in findings[0].detail

    report = audit_split(split, fit_on=leaked)
    with pytest.raises(ValueError, match="scaler: scaler was fit on 12 window"):
        report.raise_for_leaks()


def test_a_scaler_fit_on_the_whole_stream_is_caught() -> None:
    split = clean_split()
    everything = (*split.train, *split.valid, *split.test)

    report = audit_split(split, fit_on=everything)

    assert report.kinds() == frozenset({LeakKind.SCALER})


def test_a_scaler_fit_on_a_subset_of_train_is_clean() -> None:
    split = clean_split()

    assert check_scaler_leakage(split.train[:5], split) == ()


# --- hand-built bad splits ----------------------------------------------


def shifted(split: Split[FlowRecord], **overrides: object) -> Split[FlowRecord]:
    """Rebuild a split with one fold replaced, keeping the rest."""
    fields: dict[str, object] = {
        "train": split.train,
        "valid": split.valid,
        "test": split.test,
        "test_cutoff": split.test_cutoff,
        "valid_cutoff": split.valid_cutoff,
        "dropped": split.dropped,
    }
    fields.update(overrides)
    return Split(**fields)  # type: ignore[arg-type]


def test_time_leakage_is_caught_when_test_is_not_later() -> None:
    """The audit must not trust that the split came from split_windows."""
    split = clean_split()
    forged = shifted(split, test=split.train[-4:])

    report = audit_split(forged)

    assert LeakKind.TIME in report.kinds()
    assert any("no later than" in finding.detail for finding in report.findings)


def test_entity_leakage_is_caught() -> None:
    split = clean_split()
    forged = shifted(split, test=(*split.test, *split.train[:2]))

    report = audit_split(forged)

    assert LeakKind.ENTITY in report.kinds()
    detail = next(f.detail for f in report.findings if f.kind is LeakKind.ENTITY)
    assert "10.4.20.11" in detail


def test_record_leakage_is_caught_independently() -> None:
    """The shared window is reported as its own finding, not folded into the rest."""
    split = clean_split()
    shared = split.test[:1]
    forged = shifted(split, train=(*split.train, *shared))

    report = audit_split(forged)

    assert LeakKind.RECORD in report.kinds()


def test_an_empty_fold_is_reported_rather_than_passed() -> None:
    split = clean_split()
    forged = shifted(split, test=())

    report = audit_split(forged)

    assert any("a fold is empty" in finding.detail for finding in report.findings)


# --- label leakage -------------------------------------------------------


def test_a_perfectly_separating_feature_is_flagged() -> None:
    """Interleaved labels, one feature that splits them cleanly."""
    rows = [row(100.0, "normal"), row(900.0, "DoS"), row(120.0, "normal"), row(880.0, "DoS")]

    findings = check_label_leakage(rows)

    assert [finding.kind for finding in findings] == [LeakKind.LABEL]
    assert "'src_bytes'" in findings[0].detail


def test_overlapping_features_are_not_flagged() -> None:
    """Real features are noisy; overlap must not look like leakage."""
    rows = [row(100.0, "normal"), row(200.0, "DoS"), row(300.0, "normal"), row(400.0, "DoS")]

    assert check_label_leakage(rows) == ()


def test_a_single_label_cannot_be_assessed() -> None:
    rows = [row(100.0, "normal"), row(900.0, "normal")]

    assert check_label_leakage(rows) == ()


def test_three_labels_must_also_be_contiguous_to_be_flagged() -> None:
    # In `clean` the second "a" sorts between b and c, so no single threshold
    # separates the three labels; in `leaky` it sorts next to the first "a".
    clean = [row(100.0, "a"), row(200.0, "b"), row(300.0, "c"), row(250.0, "a")]
    leaky = [row(100.0, "a"), row(200.0, "b"), row(300.0, "c"), row(120.0, "a")]

    assert check_label_leakage(clean) == ()
    assert len(check_label_leakage(leaky)) == 1


def test_label_leakage_is_reported_through_audit_split() -> None:
    split = clean_split()
    rows = [row(100.0, "normal"), row(900.0, "DoS")]

    report = audit_split(split, fit_on=split.train, rows=rows)

    assert report.kinds() == frozenset({LeakKind.LABEL})


# --- reporting -----------------------------------------------------------


def test_findings_render_and_collect() -> None:
    finding = Finding(LeakKind.SCALER, "detail here", value=2.0)
    report = AuditReport(findings=(finding, Finding(LeakKind.TIME, "and here")))

    assert str(finding) == "scaler: detail here"
    assert report.ok is False
    assert report.kinds() == frozenset({LeakKind.SCALER, LeakKind.TIME})


def test_every_finding_is_reported_in_one_pass() -> None:
    """One run surfaces all of them instead of failing on the first."""
    split = clean_split()
    forged = shifted(split, test=(*split.test, *split.train[:2]))

    report = audit_split(forged, fit_on=(*split.train, *split.valid))

    assert len(report.kinds()) >= 2, report.findings
    with pytest.raises(ValueError) as excinfo:
        report.raise_for_leaks()
    assert "scaler" in str(excinfo.value)


# --- integration ---------------------------------------------------------


def test_the_whole_synthetic_pipeline_audits_clean() -> None:
    """Windowing, splitting, extraction and audit over one stream."""
    split = clean_split()
    rows = [
        extracted
        for window in (*split.train, *split.valid, *split.test)
        for extracted in extract_flow_window(window.records)
    ]

    report = audit_split(split, fit_on=split.train, rows=rows)

    assert report.ok is True, report.findings
    assert len(rows) == 180


def test_windows_are_comparable_by_identity() -> None:
    """The audit keys windows on entity plus start, so rebuilt windows match."""
    split = clean_split()
    rebuilt = window_flows(
        sorted(
            (record for window in split.train for record in window.records),
            key=lambda record: record.timestamp,
        ),
        size=5,
    )

    assert check_scaler_leakage(rebuilt, split) == ()


def test_window_type_is_usable_as_a_hint() -> None:
    """Kept trivial on purpose: the audit's public surface must stay importable."""
    split = clean_split()

    assert isinstance(split.train[0], Window)


def varied_flows(host: str, start: datetime, scale: float) -> list[FlowRecord]:
    """``host_flows`` with byte volumes scaled, so folds can differ statistically."""
    return [
        record.model_copy(update={"src_bytes": int(1200 * scale), "dst_bytes": int(3400 * scale)})
        for record in host_flows(host, start)
    ]


def varied_split() -> Split[FlowRecord]:
    """``clean_split``'s shape, but each time band carries a different byte volume.

    ``host_flows`` gives every flow identical byte counts, so the training fold
    and the whole dataset have the *same* statistics and no scaler check can tell
    them apart — measured, not assumed: column 0 holds one distinct value across
    all 120 rows. Varying the volume by band gives the folds different means,
    which is what catches a scaler fit on the wrong rows.
    """
    bands = (
        (("10.4.21.11", "10.4.21.12"), 1.0),
        (("10.4.21.13", "10.4.21.14"), 3.0),
        (("10.4.21.15", "10.4.21.16"), 9.0),
    )
    flows: list[FlowRecord] = []
    for band, (hosts, scale) in enumerate(bands):
        for host in hosts:
            flows.extend(varied_flows(host, EPOCH + timedelta(seconds=band * 40), scale))
    flows.sort(key=lambda record: record.timestamp)
    return split_windows(window_flows(flows, size=5), test_fraction=1 / 3, valid_fraction=0.5)


# --- T-203: auditing the trained artifact, not the caller's claim ----------


def numeric_rows(windows: Sequence[Window[FlowRecord]]) -> list[list[float]]:
    """The numeric vectors of a fold, as a scaler would be fit on them."""
    return [
        list(feature.numeric)
        for window in windows
        for feature in extract_flow_window(window.records, key=window.key_kind)
    ]


def test_a_scaler_fit_on_training_alone_passes_the_artifact_check() -> None:
    split = clean_split()
    rows = numeric_rows(split.train)
    scaler = StandardScaler.fit(rows, NUMERIC_FEATURES)

    assert check_scaler_statistics(scaler, rows) == ()


def test_refitting_the_scaler_on_the_full_dataset_fails_the_audit() -> None:
    """T-203's acceptance criterion, stated as the task states it (R-62).

    A scaler fit on train plus test encodes the held-out distribution into every
    standardised value, so the reported metric describes the leak. This is the
    single most common way an intrusion-detection result becomes fiction.
    """
    split = varied_split()
    train_rows = numeric_rows(split.train)
    all_rows = numeric_rows(split.train) + numeric_rows(split.test)
    leaked = StandardScaler.fit(all_rows, NUMERIC_FEATURES)

    findings = check_scaler_statistics(leaked, train_rows)

    assert findings, "a scaler fit on the full dataset must not pass"
    assert findings[0].kind is LeakKind.SCALER
    assert "beyond the training split" in findings[0].detail


def test_the_artifact_check_catches_a_caller_who_misdeclares_fit_on() -> None:
    """Why T-203 is not just T-111 run again.

    The provenance check audits what the caller says it fit on. A caller that
    fits on everything and passes ``fit_on=split.train`` satisfies it. Only the
    statistic check sees the scaler itself, so only it can fail this run.
    """
    split = varied_split()
    train_rows = numeric_rows(split.train)
    leaked = StandardScaler.fit(train_rows + numeric_rows(split.test), NUMERIC_FEATURES)

    report = audit_trained(split, leaked, train_rows, fit_on=split.train)

    assert not report.ok
    assert LeakKind.SCALER in report.kinds()
    # The provenance check alone would have found nothing.
    assert check_scaler_leakage(split.train, split) == ()


def test_a_clean_trained_run_passes_the_full_audit() -> None:
    split = clean_split()
    train_rows = numeric_rows(split.train)
    scaler = StandardScaler.fit(train_rows, NUMERIC_FEATURES)
    rows = [
        feature
        for window in split.train
        for feature in extract_flow_window(window.records, key=window.key_kind)
    ]

    report = audit_trained(split, scaler, train_rows, rows=rows, fit_on=split.train)

    report.raise_for_leaks()
    assert report.ok


def test_a_leaking_run_blocks_release() -> None:
    """The audit is a release blocker, so it must actually raise."""
    split = varied_split()
    train_rows = numeric_rows(split.train)
    leaked = StandardScaler.fit(train_rows + numeric_rows(split.test), NUMERIC_FEATURES)

    report = audit_trained(split, leaked, train_rows)

    with pytest.raises(ValueError, match="leakage audit failed"):
        report.raise_for_leaks()


def test_the_tolerance_is_relative_so_large_features_do_not_false_positive() -> None:
    """Bytes-per-second and seconds differ by orders of magnitude.

    One absolute tolerance cannot serve both: tight enough for a fraction of a
    second, it would flag floating-point noise on a byte count.
    """
    rows = [[1e9, 0.001], [2e9, 0.002], [3e9, 0.003]]
    scaler = StandardScaler.fit(rows, ("bytes", "seconds"))

    assert check_scaler_statistics(scaler, rows) == ()


def test_an_empty_or_ragged_training_fold_is_reported_not_crashed() -> None:
    scaler = StandardScaler.fit([[1.0, 2.0]], ("a", "b"))

    empty = check_scaler_statistics(scaler, [])
    assert empty and "no rows" in empty[0].detail

    ragged = check_scaler_statistics(scaler, [[1.0], [2.0]])
    assert ragged and "expected 2" in ragged[0].detail


def time_violating(temporal_enforced: bool, entity_disjoint_enforced: bool) -> Split[FlowRecord]:
    """A split whose test fold precedes its training fold, so time leaks.

    ``varied_split`` comes from ``split_windows`` and already satisfies the
    temporal invariant, so it produces no time finding to classify. Swapping the
    train and test folds makes the violation real rather than asserted.
    """
    base = varied_split()
    return Split(
        train=base.test,
        valid=base.valid,
        test=base.train,
        test_cutoff=base.test_cutoff,
        valid_cutoff=base.valid_cutoff,
        dropped=base.dropped,
        entity_disjoint_enforced=entity_disjoint_enforced,
        temporal_enforced=temporal_enforced,
    )


def test_a_leak_the_split_declares_does_not_block() -> None:
    """An entity-only or family-holdout split says it ignores time; that is policy.

    Blocking on it would make the policy unusable, and the alternative - quietly
    not reporting it - is worse. So it is reported and classified, not hidden.
    """
    split = time_violating(temporal_enforced=False, entity_disjoint_enforced=False)
    report = audit_trained(split, StandardScaler.fit([[1.0]], ("a",)), [[1.0]])

    assert any(f.kind is LeakKind.TIME for f in report.findings)
    assert all(f.kind is not LeakKind.TIME for f in blocking_findings(report, split))


def test_the_same_leak_blocks_when_the_split_claims_to_prevent_it() -> None:
    """Same finding, opposite verdict: the split's declaration is what decides."""
    split = time_violating(temporal_enforced=True, entity_disjoint_enforced=True)
    report = audit_trained(split, StandardScaler.fit([[1.0]], ("a",)), [[1.0]])

    assert any(f.kind is LeakKind.TIME for f in blocking_findings(report, split))


def test_scaler_leaks_block_under_every_policy() -> None:
    """No policy declares itself permitted to fit on held-out data."""
    split = time_violating(temporal_enforced=False, entity_disjoint_enforced=False)
    train_rows = numeric_rows(split.train)
    leaked = StandardScaler.fit(train_rows + numeric_rows(split.test), NUMERIC_FEATURES)
    report = audit_trained(split, leaked, train_rows)

    assert any(f.kind is LeakKind.SCALER for f in blocking_findings(report, split))
