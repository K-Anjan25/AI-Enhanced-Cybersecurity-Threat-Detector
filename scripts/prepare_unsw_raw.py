"""Prepare the raw UNSW-NB15 CSV parts for the repo's parsers.

Input: ``UNSW-NB15_{1..4}.csv`` or ``UNSW-NB15_{1..4}.csv.gz`` under ``--src``.
Each raw part is checked against its published SHA-256 and row count before
anything is written. Output: ``headered_{1..4}.csv`` under ``--out``, with the
official 49-column header (the raw parts have none) and any UTF-8 BOM removed.

``--sample-frac`` keeps a deterministic fraction of rows per part, for machines
without enough RAM for the full 2.54M-row corpus (about 6 GB peak parse).
Hashes are always checked on the full raw part, never on the sample.

Usage:
    python scripts/prepare_unsw_raw.py --src data/raw/unsw --out data/raw/unsw
    python scripts/prepare_unsw_raw.py --src data/raw/unsw --out data/raw/unsw --sample-frac 0.15
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import random
import sys
from pathlib import Path
from typing import BinaryIO

HEADER = (
    b"srcip,sport,dstip,dsport,proto,state,dur,sbytes,dbytes,sttl,dttl,sloss,dloss,"
    b"service,sload,dload,spkts,dpkts,swin,dwin,stcpb,dtcpb,smeansz,dmeansz,"
    b"trans_depth,res_bdy_len,sjit,djit,stime,ltime,sintpkt,dintpkt,tcprtt,synack,"
    b"ackdat,is_sm_ips_ports,ct_state_ttl,ct_flw_http_mthd,is_ftp_login,ct_ftp_cmd,"
    b"ct_srv_src,ct_srv_dst,ct_dst_ltm,ct_src_ltm,ct_src_dport_ltm,ct_dst_sport_ltm,"
    b"ct_dst_src_ltm,attack_cat,label\n"
)

#: Published SHA-256 and row count of each raw part (UNSW-NB15 official release).
EXPECTED: dict[int, tuple[str, int]] = {
    1: ("7d851bbeabd27894ce39c8e78835c73341fc946652fb7743b9eff193b55eb511", 700_001),
    2: ("6130ad02873cc6069ae695cf2844f2e8c2e9a9a1b7532dd82ab8f202757cacf8", 700_001),
    3: ("ae990a96c3dfcd425ce2801aadb1727a34d5e0ae6d8215dbcdae60dedfaef640", 700_001),
    4: ("cdf563692d51d405541dd659ddcdad9fa01f001f05fe9fc4b67f00ca12fbc96a", 440_044),
}

BOM = b"\xef\xbb\xbf"


def _find_raw(src: Path, index: int) -> tuple[Path, bool]:
    """Return ``(path, is_gzip)`` for part ``index``, preferring a plain CSV."""
    plain = src / f"UNSW-NB15_{index}.csv"
    if plain.exists():
        return plain, False
    gz = src / f"UNSW-NB15_{index}.csv.gz"
    if gz.exists():
        return gz, True
    raise FileNotFoundError(f"missing UNSW-NB15_{index}.csv(.gz) under {src}")


def _open_raw(path: Path, is_gzip: bool) -> BinaryIO:
    return gzip.open(path, "rb") if is_gzip else open(path, "rb")


def _check_and_write(src: Path, out: Path, index: int, frac: float, seed: int) -> int:
    """Verify part ``index`` against EXPECTED and write its headered (sampled) copy.

    Returns the number of rows written. Raises ValueError on a hash or row-count
    mismatch, before the headered file is considered complete.
    """
    expected_sha, expected_rows = EXPECTED[index]
    raw_path, is_gzip = _find_raw(src, index)
    digest = hashlib.sha256()
    rows_total = 0
    rows_written = 0
    rng = random.Random(seed + index)  # noqa: S311 - sampling, not cryptography
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"headered_{index}.csv"
    tmp = target.with_suffix(".csv.partial")

    with _open_raw(raw_path, is_gzip) as stream, open(tmp, "wb") as dst:
        dst.write(HEADER)
        first = True
        for line in stream:
            digest.update(line)
            rows_total += 1
            if first:
                first = False
                if line.startswith(BOM):
                    line = line[len(BOM) :]
            if frac >= 1.0 or rng.random() < frac:
                dst.write(line)
                rows_written += 1

    if digest.hexdigest() != expected_sha:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"part {index}: sha256 {digest.hexdigest()} != expected {expected_sha}")
    if rows_total != expected_rows:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"part {index}: {rows_total} rows != expected {expected_rows}")

    tmp.replace(target)
    return rows_written


def main(argv: list[str] | None = None) -> int:
    """Verify each raw part and write the headered (optionally sampled) copies."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", required=True, type=Path, help="folder with the raw parts")
    parser.add_argument("--out", required=True, type=Path, help="folder for headered parts")
    parser.add_argument(
        "--sample-frac",
        type=float,
        default=1.0,
        help="fraction of rows to keep per part (1.0 = full corpus)",
    )
    parser.add_argument("--seed", type=int, default=20260114)
    args = parser.parse_args(argv)

    if not 0.0 < args.sample_frac <= 1.0:
        parser.error("--sample-frac must be in (0, 1]")

    total = 0
    for index in sorted(EXPECTED):
        try:
            written = _check_and_write(args.src, args.out, index, args.sample_frac, args.seed)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        total += written
        print(f"part {index}: verified, wrote {written} rows")
    print(f"total rows written: {total} (sample-frac {args.sample_frac})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
