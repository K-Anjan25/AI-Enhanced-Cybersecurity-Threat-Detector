"""Public dataset manifest (T-101, T-102).

One frozen record per downloadable file, holding everything the inventory in
memory.md §"Data sources" claims: where it came from, its SHA-256, its exact
byte size, its row count and what is wrong with it.

This module is the single source of truth. ``scripts/fetch_datasets.py`` reads
it to decide what to download and what hash to expect, and
``tests/test_datasets.py`` asserts the prose inventory agrees with it. Neither
the script nor the doc may carry its own copy of a checksum.

Two things a reader should not have to rediscover:

* ``usable_for_splits`` is a load-bearing flag, not decoration. A file without
  source/destination addresses cannot be split entity-disjointly (R-61) and one
  without timestamps cannot be split temporally (R-60). The widely mirrored
  ``UNSW_NB15_training-set.csv`` is missing both, so it is recorded as
  unavailable for the pipeline even though it is the file almost every
  benchmark paper actually used.
* Every mirror below is a third-party re-upload, not the publisher. Hashes are
  what was measured when the file was fetched, and ``canonical_source`` is where
  a reader who needs the authoritative artifact should go.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DatasetId = Literal["unsw-nb15", "cic-ids2017", "bgl"]

#: Where files land, relative to the repository root. Ignored by git (R-40).
RAW_DIR = "data/raw"

#: GitHub's contents endpoint serves file bytes when the raw media type is
#: requested, and does so without authentication for public repositories. It is
#: used instead of raw.githubusercontent.com, which some sandboxes cannot
#: reach. Unauthenticated callers are rate limited to 60 requests/hour.
GITHUB_CONTENTS_URL = "https://api.github.com/repos/{repo}/contents/{path}"


class DatasetFile(BaseModel):
    """One downloadable dataset file and its verification data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: DatasetId
    file_name: str = Field(description="Name under data/raw/.")

    # Provenance
    repo: str = Field(description="GitHub 'owner/name' the copy was taken from.")
    path: str = Field(description="Path of the file inside that repository.")
    canonical_source: str = Field(description="The publisher's own download page.")
    licence: str

    # Verification — measured, never transcribed from a webpage.
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(gt=0)
    row_count: int = Field(gt=0, description="Data rows, excluding the header.")
    columns: int = Field(gt=0)

    # Fitness for this pipeline
    has_entity_columns: bool = Field(
        description="Source and destination addresses are present (needed by R-61)."
    )
    has_timestamps: bool = Field(description="Per-flow start times are present (needed by R-60).")
    caveats: tuple[str, ...] = ()

    @property
    def usable_for_splits(self) -> bool:
        """Whether this file can satisfy the temporal and entity split rules."""
        return self.has_entity_columns and self.has_timestamps

    @property
    def download_url(self) -> str:
        """URL the fetcher reads bytes from."""
        return GITHUB_CONTENTS_URL.format(repo=self.repo, path=self.path)


UNSW_NB15_TRAINING_DERIVATIVE = DatasetFile(
    dataset_id="unsw-nb15",
    file_name="UNSW_NB15_training-set.csv",
    repo="shailjaroy/NIDS-UNSW_NB15",
    path="data/UNSW_NB15_training-set.csv",
    canonical_source="https://research.unsw.edu.au/projects/unsw-nb15-dataset",
    licence="Free for academic research in perpetuity; commercial use by agreement. "
    "Cite Moustafa & Slay, MilCIS 2015.",
    sha256="bec7dd5ec88dc2a0ccc7a07879d338395ed7421750f675fd0339e07dfe0648fa",
    size_bytes=32_293_018,
    row_count=175_341,
    columns=45,
    has_entity_columns=False,
    has_timestamps=False,
    caveats=(
        "A 45-column derivative, not the publisher's 49-feature CSV: srcip, sport, "
        "dstip, dsport, stime and ltime are absent, so no entity or temporal split "
        "is possible. It also adds a 'rate' column that the official feature list "
        "does not enumerate.",
        "Two mirrors were found with the file names transposed — 2hyes/security_ml "
        "serves the 82,332-row test split under the name 'training-set', and "
        "SVKBlackDeath/UNSW-NB15 the reverse. Verify by hash, never by name.",
    ),
)

UNSW_NB15_TESTING_DERIVATIVE = DatasetFile(
    dataset_id="unsw-nb15",
    file_name="UNSW_NB15_testing-set.csv",
    repo="shailjaroy/NIDS-UNSW_NB15",
    path="data/UNSW_NB15_testing-set.csv",
    canonical_source="https://research.unsw.edu.au/projects/unsw-nb15-dataset",
    licence=UNSW_NB15_TRAINING_DERIVATIVE.licence,
    sha256="734fe6642edf758f7c94d7d9149426b49d202fe8e7bf0bef47392489c3c0a559",
    size_bytes=15_380_800,
    row_count=82_332,
    columns=45,
    has_entity_columns=False,
    has_timestamps=False,
    caveats=UNSW_NB15_TRAINING_DERIVATIVE.caveats,
)

UNSW_NB15_SCHEMA_SAMPLE = DatasetFile(
    dataset_id="unsw-nb15",
    file_name="unsw_nb15_official_schema_sample.csv",
    repo="luna866/UNSW-NB15",
    path="sample_train10.csv",
    canonical_source="https://research.unsw.edu.au/projects/unsw-nb15-dataset",
    licence=UNSW_NB15_TRAINING_DERIVATIVE.licence,
    sha256="13be3cddc8c8c2e0fe874d68841e7f0b007eaa13cf9a194a20991e0d6f41da74",
    size_bytes=2_386_163,
    row_count=10_000,
    columns=49,
    has_entity_columns=True,
    has_timestamps=True,
    caveats=(
        "A 10,000-row sample of the official 49-column schema — the only reachable "
        "copy that keeps srcip/dstip/stime/ltime. The full official CSVs are "
        "distributed from a UNSW SharePoint share, which is not reachable from "
        "this sandbox.",
        "attack_cat is an integer code rather than the official category name. The "
        "code table below was read from the mirror's own mapping.pkl and "
        "cross-checked against its binary label column (code 0 <-> label 0, every "
        "other code <-> label 1).",
    ),
)

CIC_IDS2017_FRIDDAY_DDOS = DatasetFile(
    dataset_id="cic-ids2017",
    file_name="Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
    repo="StarterArcher/CICIDS2017",
    path="Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
    canonical_source="https://www.unb.ca/cic/datasets/ids-2017.html",
    licence="Free for research and educational use. Cite Sharafaldin, Lashkari & "
    "Ghorbani, ICISSP 2018.",
    sha256="306294008927756094b069d24764bfa6519fe267a8104903c056fc9c3cf38636",
    size_bytes=36_010_816,
    row_count=225_745,
    columns=32,
    has_entity_columns=True,
    has_timestamps=True,
    caveats=(
        "One of the five capture days (Friday afternoon DDoS), not the whole "
        "dataset. Labels are BENIGN (97,718) and DDoS (128,027).",
        "32 of CICFlowMeter's 80+ features. Column names carry a leading space.",
        "Timestamps are truncated to minute precision ('07/07/2017 03:30'), so "
        "flows inside one minute have no reliable ordering. Temporal splits are "
        "still valid at minute granularity.",
    ),
)

BGL_2K = DatasetFile(
    dataset_id="bgl",
    file_name="BGL_2k.log",
    repo="logpai/loghub",
    path="BGL/BGL_2k.log",
    canonical_source="https://github.com/logpai/loghub",
    licence="LogHub datasets are free for research use; the underlying BGL logs "
    "are from the LLNL BlueGene/L supercomputer. Cite He et al., ICPC 2016.",
    sha256="2a819ea540909db682005c9cf948387a40729b5c2e9f19d430e29ce704825496",
    size_bytes=317_150,
    row_count=2_000,
    columns=1,
    has_entity_columns=True,
    has_timestamps=True,
    caveats=(
        "A raw log file, so `columns` is 1 by convention rather than a field count.",
        "Chosen over Thunderbird and the other LogHub corpora because it carries an "
        "explicit severity on every line. Thunderbird has no severity column at all, "
        "and log@1 requires one; inferring a level from message keywords would put "
        "fabricated data into the training set.",
        "Severities upstream are INFO, WARNING, ERROR, SEVERE and FATAL. SEVERE maps "
        "to `error` and FATAL to `critical`; the mapping is in `log_parsers.BGL_LEVELS`.",
        "2,000 lines parse to 1,778 distinct hosts across 5 components, which is what "
        "makes a host-keyed log window meaningful at all.",
    ),
)

BGL_2K_STRUCTURED = DatasetFile(
    dataset_id="bgl",
    file_name="BGL_2k.log_structured.csv",
    repo="logpai/loghub",
    path="BGL/BGL_2k.log_structured.csv",
    canonical_source="https://github.com/logpai/loghub",
    licence=BGL_2K.licence,
    sha256="3fe74103c0b02a28514534e2a47257a3f770135ca61afd425bbd3b9d6a31fe26",
    size_bytes=425_129,
    row_count=2_000,
    columns=13,
    has_entity_columns=True,
    has_timestamps=True,
    caveats=(
        "LogHub's own parsing of the same 2,000 lines: Node, Type, Component, Level, "
        "Content, EventId and EventTemplate. Not training data — it is the ground "
        "truth the template miner is measured against (120 distinct EventIds).",
        "Used only for verification. Never train on it: it is a derived artifact of "
        "the corpus it labels.",
    ),
)

#: Every file the fetcher knows about.
DATASETS: tuple[DatasetFile, ...] = (
    UNSW_NB15_TRAINING_DERIVATIVE,
    UNSW_NB15_TESTING_DERIVATIVE,
    UNSW_NB15_SCHEMA_SAMPLE,
    CIC_IDS2017_FRIDDAY_DDOS,
    BGL_2K,
    BGL_2K_STRUCTURED,
)

#: attack_cat codes in the UNSW sample, from the mirror's mapping.pkl.
UNSW_ATTACK_CAT_CODES: dict[int, str] = {
    0: "normal",
    1: "Exploits",
    2: "Reconnaissance",
    3: "DoS",
    4: "Generic",
    5: "Shellcode",
    6: "Fuzzers",
    7: "Worms",
    8: "Backdoor",
    9: "Analysis",
}


def by_file_name(name: str) -> DatasetFile:
    """Look a manifest entry up by its local file name."""
    for spec in DATASETS:
        if spec.file_name == name:
            return spec
    msg = f"no dataset in the manifest is named {name!r}"
    raise KeyError(msg)


def usable_for_splits() -> tuple[DatasetFile, ...]:
    """The subset of the manifest that can satisfy R-60 and R-61."""
    return tuple(spec for spec in DATASETS if spec.usable_for_splits)
