"""Tests for BGL log parsing and template mining (T-104).

The fixture is 20 real lines from the BGL corpus — four of each severity the
corpus uses — so the severity mapping and the miner are exercised on data that
actually occurs. Field values were read out of the file by hand.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from aegis_ml.data.log_parsers import (
    BGL_LEVELS,
    PARAMETER_PLACEHOLDER,
    TemplateMiner,
    lexical_template,
    parse_bgl,
    template_id,
    write_ndjson,
)
from aegis_ml.data.records import LogLevel, LogRecord

FIXTURE = Path(__file__).parent / "fixtures" / "bgl_sample.log"


def test_every_line_parses_and_none_is_lost() -> None:
    report = parse_bgl(str(FIXTURE)).report
    assert report.lines_read == 20
    assert report.parsed == 20
    assert report.unparseable == 0
    assert report.unparseable_reasons == {}
    assert report.unparseable_rate == 0.0


def test_first_record_matches_the_file_by_hand() -> None:
    """``- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 ... RAS KERNEL INFO <msg>``."""
    record = parse_bgl(str(FIXTURE)).records[0]
    assert record.host == "R02-M1-N0-C:J12-U11"
    assert record.service == "KERNEL"
    assert record.level is LogLevel.INFO
    assert record.message == "instruction cache parity error corrected"
    # The epoch column, not the human-readable date fields.
    assert record.timestamp == datetime(2005, 6, 3, 22, 42, 50, tzinfo=UTC)
    assert record.schema_version == "log@1"


def test_every_severity_maps_onto_a_log_level() -> None:
    levels = parse_bgl(str(FIXTURE)).report.levels
    # SEVERE folds into error, FATAL into critical; they do not collapse together.
    assert levels["info"] == 4
    assert levels["warning"] == 4
    assert levels["error"] == 8
    assert levels["critical"] == 4


def test_severe_and_fatal_do_not_collapse() -> None:
    assert BGL_LEVELS["SEVERE"] is LogLevel.ERROR
    assert BGL_LEVELS["FATAL"] is LogLevel.CRITICAL
    assert BGL_LEVELS["SEVERE"] is not BGL_LEVELS["FATAL"]


def test_hosts_and_services_are_reported() -> None:
    report = parse_bgl(str(FIXTURE)).report
    assert report.distinct_hosts >= 1
    assert report.distinct_services >= 1


def test_parameters_hold_the_original_values_not_the_placeholder() -> None:
    """A parameter that reads ``<*>`` has destroyed the data it abstracted."""
    miner = TemplateMiner.fit(
        ["63543 double-hummer alignment exceptions", "162 double-hummer alignment exceptions"]
    )
    mined = miner.assign("162 double-hummer alignment exceptions")
    assert mined.parameters == {"p0": "162"}
    assert PARAMETER_PLACEHOLDER not in mined.parameters.values()
    assert mined.template == f"{PARAMETER_PLACEHOLDER} double-hummer alignment exceptions"


def test_bare_hex_is_treated_as_a_parameter() -> None:
    """``003a90fc`` has no 0x prefix, but it is a register value, not a word."""
    tokens = lexical_template("iar 003a90fc dear 00b360e8")
    assert tokens == (
        "iar",
        PARAMETER_PLACEHOLDER,
        "dear",
        PARAMETER_PLACEHOLDER,
    )


def test_dotted_numeric_suffix_is_a_parameter() -> None:
    assert lexical_template("generating core.2275") == ("generating", PARAMETER_PLACEHOLDER)


def test_a_word_that_happens_to_be_hex_stays_in_the_template() -> None:
    """``dead`` is hex letters but carries no digit, so it is a word."""
    assert lexical_template("task dead") == ("task", "dead")


def test_two_varying_positions_at_once_are_not_merged() -> None:
    """A known gap, pinned rather than papered over.

    ``2,`` and ``0x0b85eee0,`` carry a comma, so neither matches a number or a
    hex literal and the lexical pass keeps them as template text. The messages
    then differ in *two* positions, and the merge pass only unifies templates
    differing in one, so all three stay separate. LogHub's labels treat them as
    one event. Measured over the whole corpus the cost is small — 0.9530
    agreement in that direction against 0.9935 the other way — but it is real,
    and it is the first thing to revisit if template quality ever matters.
    """
    messages = [
        "CE sym 2, at 0x0b85eee0, mask 0x05",
        "CE sym 20, at 0x1438f9e0, mask 0x40",
        "CE sym 7, at 0x01228120, mask 0x10",
    ]
    assert len({lexical_template(m) for m in messages}) == 3
    miner = TemplateMiner.fit(messages)
    assert len(miner.templates) == 3
    assert len({miner.assign(m).template_id for m in messages}) == 3


def test_merge_pass_unifies_messages_the_lexical_pass_splits() -> None:
    """Differing in one position the lexical rules miss still merges."""
    messages = ["node alpha reported ok", "node beta reported ok", "node gamma reported ok"]
    lexical = {lexical_template(m) for m in messages}
    miner = TemplateMiner.fit(messages)
    assert len(lexical) == 3
    assert len(miner.templates) == 1
    assert miner.templates[0] == (
        "node",
        PARAMETER_PLACEHOLDER,
        "reported",
        "ok",
    )


def test_templates_are_ordered_least_specific_first() -> None:
    """The stored order decides assignment, so it must be fixed, not incidental."""
    miner = TemplateMiner.fit(
        ["node alpha reported ok", "node beta reported ok", "node alpha reported fine"]
    )
    wildcards = [sum(1 for token in t if token == PARAMETER_PLACEHOLDER) for t in miner.templates]
    assert wildcards == sorted(wildcards, reverse=True)


def test_mining_is_deterministic() -> None:
    """Two fits over the same corpus must agree exactly (R-67)."""
    messages = ["a 1 b", "a 2 b", "c 3 d"]
    assert TemplateMiner.fit(messages) == TemplateMiner.fit(list(reversed(messages)))


def test_template_ids_are_content_addressed() -> None:
    assert template_id("x y") == template_id("x y")
    assert template_id("x y") != template_id("x z")
    assert len(template_id("x y")) == 16


def test_unparseable_lines_are_counted_with_a_reason(tmp_path: Path) -> None:
    target = tmp_path / "bgl.log"
    good = FIXTURE.read_text(encoding="utf-8").splitlines()[0]
    target.write_text(f"{good}\nthis is not a bgl line\n", encoding="utf-8")
    report = parse_bgl(str(target)).report
    assert report.lines_read == 2
    assert report.parsed == 1
    assert report.unparseable == 1
    assert report.unparseable_reasons == {"shape_mismatch": 1}
    assert report.unparseable_rate == 0.5


def test_an_unknown_severity_is_counted_not_guessed(tmp_path: Path) -> None:
    target = tmp_path / "bgl.log"
    line = FIXTURE.read_text(encoding="utf-8").splitlines()[0]
    target.write_text(line.replace(" INFO ", " TRACE ") + "\n", encoding="utf-8")
    report = parse_bgl(str(target)).report
    assert report.parsed == 0
    assert report.unparseable_reasons == {"unmapped_level:TRACE": 1}


def test_empty_lines_are_counted(tmp_path: Path) -> None:
    target = tmp_path / "bgl.log"
    good = FIXTURE.read_text(encoding="utf-8").splitlines()[0]
    target.write_text(f"{good}\n\n   \n", encoding="utf-8")
    report = parse_bgl(str(target)).report
    assert report.unparseable_reasons == {"empty_line": 2}
    assert report.parsed == 1


def test_raise_for_empty_names_the_reasons(tmp_path: Path) -> None:
    target = tmp_path / "bgl.log"
    target.write_text("garbage\n", encoding="utf-8")
    result = parse_bgl(str(target))
    with pytest.raises(ValueError, match="shape_mismatch=1"):
        result.report.raise_for_empty()


def test_raise_for_empty_passes_when_something_parsed() -> None:
    parse_bgl(str(FIXTURE)).report.raise_for_empty()


def test_template_text_maps_ids_back_to_templates() -> None:
    parsed = parse_bgl(str(FIXTURE))
    for tid, text in parsed.template_text.items():
        assert tid in parsed.template_counts
        assert text
    assert set(parsed.template_text) == set(parsed.template_counts)


def test_write_ndjson_round_trips_through_log_record(tmp_path: Path) -> None:
    records = parse_bgl(str(FIXTURE)).records
    out = tmp_path / "logs.ndjson"
    assert write_ndjson(records, str(out)) == len(records)
    restored = [LogRecord.model_validate_json(line) for line in out.read_text().splitlines()]
    assert restored == list(records)


def test_mining_converges() -> None:
    miner = TemplateMiner.fit(["a 1 b", "a 2 b"])
    assert miner.converged
    assert miner.merge_rounds >= 1
