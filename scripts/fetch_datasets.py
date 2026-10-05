#!/usr/bin/env python3
"""Download the public benchmark datasets and verify them (T-101).

Every byte this script writes is checked against a SHA-256 in
``aegis_ml.data.datasets``. The manifest is the only place a hash appears:
neither this file nor memory.md carries its own copy, and ``test_datasets.py``
fails if the two ever disagree.

Behaviour:

  * A file already on disk with the right hash is verified and left alone — it
    is never re-downloaded.
  * A file on disk with the wrong hash is an error naming the expected and
    actual digest. It is not silently replaced, because a partial or tampered
    file that quietly becomes a different file is how a training run ends up
    measuring the wrong data.
  * A download that lands at the wrong size or hash is deleted, so a failed run
    cannot leave a corrupt artifact behind for the next one to trust.

Usage::

    python scripts/fetch_datasets.py              # everything in the manifest
    python scripts/fetch_datasets.py --only unsw-nb15
    python scripts/fetch_datasets.py --list       # no network

Only the files marked usable for splits are needed for model work; ``--list``
shows which those are and why the others are not.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request
from enum import StrEnum
from typing import BinaryIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml-service"))

from aegis_ml.data.datasets import DATASETS, RAW_DIR, DatasetFile  # noqa: E402

CHUNK = 1 << 20
USER_AGENT = "aegis-dataset-fetcher/0.1"


class FetchStatus(StrEnum):
    """What happened to one file."""

    DOWNLOADED = "downloaded"
    VERIFIED = "verified"


class ChecksumMismatch(RuntimeError):
    """A file on disk or just downloaded does not match the manifest."""

    def __init__(self, spec: DatasetFile, actual: str) -> None:
        """Record the manifest entry and the digest that was actually found."""
        self.spec = spec
        self.actual = actual
        super().__init__(
            f"{spec.file_name}: sha256 mismatch\n"
            f"  expected: {spec.sha256}\n"
            f"  actual:   {actual}\n"
            f"  source:   {spec.download_url}\n"
            f"Refusing to use it. Delete the file to force a re-download."
        )


def sha256_of(path: str) -> str:
    """Hex SHA-256 of a file, read in chunks so a 36 MB CSV does not sit in RAM."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify(spec: DatasetFile, path: str) -> bool:
    """True when the file at ``path`` matches the manifest exactly."""
    if not os.path.isfile(path):
        return False
    if os.path.getsize(path) != spec.size_bytes:
        return False
    return sha256_of(path) == spec.sha256


def _download(spec: DatasetFile, path: str) -> None:
    """Stream ``spec`` to ``path``, atomically via a temporary file."""
    request = urllib.request.Request(  # noqa: S310 - URL comes from the manifest
        spec.download_url,
        headers={"Accept": "application/vnd.github.raw", "User-Agent": USER_AGENT},
    )
    tmp = f"{path}.part"
    try:
        with urllib.request.urlopen(request) as source:  # noqa: S310
            _copy(source, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _copy(source: BinaryIO, tmp: str) -> None:
    with open(tmp, "wb") as sink:
        while chunk := source.read(CHUNK):
            sink.write(chunk)


def fetch(spec: DatasetFile, dest_dir: str) -> FetchStatus:
    """Ensure one manifest file is present and correct.

    Raises:
        ChecksumMismatch: the file exists but does not match, or the download
            did not match.
    """
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, spec.file_name)

    if os.path.isfile(path):
        if verify(spec, path):
            return FetchStatus.VERIFIED
        raise ChecksumMismatch(spec, sha256_of(path))

    _download(spec, path)
    if not verify(spec, path):
        actual = sha256_of(path)
        os.unlink(path)
        raise ChecksumMismatch(spec, actual)
    return FetchStatus.DOWNLOADED


def _report(spec: DatasetFile, status: FetchStatus) -> None:
    mark = "=" if status is FetchStatus.VERIFIED else "+"
    print(f"  {mark} {spec.file_name:<48} {status.value}  {spec.size_bytes:>11,} bytes")


def main(argv: list[str] | None = None) -> int:
    """Fetch the manifest. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--only",
        choices=sorted({s.dataset_id for s in DATASETS}),
        help="Fetch just one dataset.",
    )
    parser.add_argument(
        "--file",
        action="append",
        choices=[s.file_name for s in DATASETS],
        help="Fetch one specific file. Repeatable.",
    )
    parser.add_argument(
        "--list", action="store_true", help="Print the manifest and exit."
    )
    parser.add_argument(
        "--dest",
        default=os.path.join(ROOT, RAW_DIR),
        help=f"Target directory (default: {RAW_DIR}).",
    )
    args = parser.parse_args(argv)

    specs = DATASETS
    if args.only is not None:
        specs = tuple(s for s in specs if s.dataset_id == args.only)
    if args.file:
        wanted = set(args.file)
        specs = tuple(s for s in specs if s.file_name in wanted)
    if not specs:
        parser.error("the --only/--file filters selected nothing")

    if args.list:
        for spec in specs:
            fit = (
                "usable for R-60/R-61 splits"
                if spec.usable_for_splits
                else (
                    "NOT usable for splits: missing "
                    + ", ".join(
                        n
                        for n, ok in (
                            ("addresses", spec.has_entity_columns),
                            ("timestamps", spec.has_timestamps),
                        )
                        if not ok
                    )
                )
            )
            print(f"{spec.dataset_id}  {spec.file_name}")
            digest = spec.sha256[:16]
            print(
                f"    {spec.row_count:>9,} rows x {spec.columns} cols   sha256={digest}…"
            )
            print(f"    {fit}")
            for caveat in spec.caveats:
                print(f"    note: {caveat}")
        return 0

    print(f"fetching {len(specs)} file(s) into {args.dest}")
    failures: list[str] = []
    for spec in specs:
        try:
            _report(spec, fetch(spec, args.dest))
        except ChecksumMismatch as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            failures.append(spec.file_name)
        except OSError as exc:
            print(f"FAILED {spec.file_name}: {exc}", file=sys.stderr)
            failures.append(spec.file_name)

    if failures:
        print(f"\n{len(failures)} of {len(specs)} file(s) failed", file=sys.stderr)
        return 1
    print(f"\nall {len(specs)} file(s) present and verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
