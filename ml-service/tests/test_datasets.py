"""Tests for the dataset manifest (T-101, T-102).

T-102's acceptance criterion is that "script output and doc agree (checked by a
test)". That is what ``test_every_manifest_hash_appears_in_memory_md`` does: the
inventory in memory.md is the human-facing claim, ``datasets.py`` is the
machine-facing one, and neither is allowed to drift from the other. A checksum
typed into a document by hand is a checksum that will eventually be wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from aegis_ml.data.datasets import (
    DATASETS,
    UNSW_ATTACK_CAT_CODES,
    DatasetFile,
    by_file_name,
    usable_for_splits,
)

MEMORY = Path(__file__).resolve().parents[2] / "memory.md"
SHA256_RE = re.compile(r"\b[0-9a-f]{64}\b")


def test_every_entry_carries_a_well_formed_hash() -> None:
    for spec in DATASETS:
        assert len(spec.sha256) == 64
        assert SHA256_RE.fullmatch(spec.sha256), spec.file_name


def test_no_file_appears_twice() -> None:
    names = [spec.file_name for spec in DATASETS]
    assert len(names) == len(set(names))


def test_by_file_name_round_trips() -> None:
    for spec in DATASETS:
        assert by_file_name(spec.file_name) is spec
    with pytest.raises(KeyError, match="no dataset in the manifest"):
        by_file_name("not-a-dataset.csv")


def test_usable_for_splits_requires_both_addresses_and_timestamps() -> None:
    """Neither invariant alone is enough: R-60 needs time, R-61 needs entities."""
    usable = usable_for_splits()
    assert usable
    for spec in usable:
        assert spec.has_entity_columns and spec.has_timestamps
    for spec in DATASETS:
        if spec in usable:
            continue
        assert not (spec.has_entity_columns and spec.has_timestamps)


def test_the_45_column_derivatives_are_flagged_unusable() -> None:
    """The files most papers use cannot support this project's split rules."""
    for name in ("UNSW_NB15_training-set.csv", "UNSW_NB15_testing-set.csv"):
        spec = by_file_name(name)
        assert spec.columns == 45
        assert not spec.usable_for_splits
        assert any("srcip" in caveat for caveat in spec.caveats)


def test_row_counts_match_the_publisher_for_unsw() -> None:
    """UNSW documents 175,341 training and 82,332 testing records."""
    assert by_file_name("UNSW_NB15_training-set.csv").row_count == 175_341
    assert by_file_name("UNSW_NB15_testing-set.csv").row_count == 82_332


def test_every_manifest_hash_appears_in_memory_md() -> None:
    document = MEMORY.read_text(encoding="utf-8")
    documented = set(SHA256_RE.findall(document))
    for spec in DATASETS:
        assert (
            spec.sha256 in documented
        ), f"{spec.file_name} is in the manifest but its hash is not in memory.md"


def test_row_counts_in_memory_md_match_the_manifest() -> None:
    """Catches a transposed or retyped count in the prose table."""
    document = MEMORY.read_text(encoding="utf-8")
    for spec in DATASETS:
        assert spec.sha256 in document
        # The row count and the hash must appear on the same table row.
        line = next(
            (ln for ln in document.splitlines() if spec.sha256 in ln),
            "",
        )
        assert f"{spec.row_count:,}" in line, (
            f"{spec.file_name}: manifest says {spec.row_count:,} rows, "
            f"but that is not on its memory.md line: {line!r}"
        )


def test_no_hash_is_documented_without_a_manifest_entry() -> None:
    """The reverse direction: a stale hash left behind in the doc."""
    document = MEMORY.read_text(encoding="utf-8")
    section = document[document.index("## Data sources") : document.index("## Constraints")]
    known = {spec.sha256 for spec in DATASETS}
    for found in SHA256_RE.findall(section):
        assert found in known, f"memory.md documents a hash with no manifest entry: {found}"


def test_attack_cat_codes_cover_normal_and_the_nine_categories() -> None:
    """The code table came from a mirror's pickle; it must match the published set."""
    assert UNSW_ATTACK_CAT_CODES[0] == "normal"
    attacks = {name for code, name in UNSW_ATTACK_CAT_CODES.items() if code != 0}
    assert attacks == {
        "Fuzzers",
        "Analysis",
        "Backdoor",
        "DoS",
        "Exploits",
        "Generic",
        "Reconnaissance",
        "Shellcode",
        "Worms",
    }
    assert sorted(UNSW_ATTACK_CAT_CODES) == list(range(10))


def test_download_url_points_at_the_reachable_endpoint() -> None:
    """raw.githubusercontent.com cannot be reached from the sandbox; the API can."""
    spec: DatasetFile = DATASETS[0]
    assert spec.download_url.startswith("https://api.github.com/repos/")
    assert "raw.githubusercontent.com" not in spec.download_url
    assert spec.repo in spec.download_url
    assert spec.path in spec.download_url


def test_every_entry_names_a_canonical_source_and_licence() -> None:
    for spec in DATASETS:
        assert spec.canonical_source.startswith("https://")
        assert len(spec.licence) > 20, spec.file_name
