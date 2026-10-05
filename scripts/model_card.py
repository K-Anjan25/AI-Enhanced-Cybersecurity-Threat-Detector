#!/usr/bin/env python
r"""Build a release model card from recorded runs (T-214, R-74).

    python scripts/model_card.py --model-id flownet@1.0.0 --kind flow \
        --metric "Transfer recall=data/runs/transfer.json:recall" \
        --metric "Scoring p95 ms=data/runs/inference.json:latency_ms.p95" \
        --limitation "Evaluated on one pair of captures." \
        --out data/runs/model_card.md --json-out data/runs/model_card.json

No metric value is accepted on the command line. Each ``--metric`` names an
artifact and a field inside it, and the value is read from that file at build
time. That is the whole design: R-74 treats a fabricated number as an honesty
defect, and the only way to keep that from happening by accident is to make the
typed-in number impossible to express.

``--limitation`` is free text and must be supplied. Limitations are judgements
rather than measurements, so they cannot be read from a run — but a card with none
is refused, because every number here came from a specific corpus and a card that
does not say so reads as a general claim.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml-service"))
sys.path.insert(0, ROOT)

from aegis_ml.registry.model_card import (  # noqa: E402
    DEFAULT_ADVERSARIAL_CAVEAT,
    build_card,
    load_metric,
)


def _resolve(path: str) -> str:
    """Make a run-artifact path absolute against the repository."""
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def main(argv: list[str] | None = None) -> int:
    """Read the cited runs and emit a card whose numbers all came from them."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--intended-use", required=True)
    parser.add_argument(
        "--metric",
        action="append",
        required=True,
        metavar="NAME=ARTIFACT:FIELD.PATH",
        help="repeatable; the value is read from the artifact, never typed here",
    )
    parser.add_argument(
        "--limitation",
        action="append",
        required=True,
        help="repeatable; free text, and a card with none is refused",
    )
    parser.add_argument("--adversarial-caveat", default=DEFAULT_ADVERSARIAL_CAVEAT)
    parser.add_argument("--out", required=True)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args(argv)

    metrics = []
    for spec in args.metric:
        if "=" not in spec or ":" not in spec.split("=", 1)[1]:
            print(
                f"--metric {spec!r} must look like NAME=ARTIFACT:FIELD.PATH",
                file=sys.stderr,
            )
            return 2
        name, rest = spec.split("=", 1)
        artifact, field = rest.rsplit(":", 1)
        metrics.append(load_metric(_resolve(artifact), name.strip(), *field.split(".")))
        print(f"  {name.strip():28s} {metrics[-1].value:g}  <- {artifact} : {field}")

    card = build_card(
        model_id=args.model_id,
        kind=args.kind,
        intended_use=args.intended_use,
        metrics=metrics,
        limitations=list(args.limitation),
        adversarial_caveat=args.adversarial_caveat,
    )

    out = _resolve(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(card.as_markdown())
    print(f"wrote {out}")

    if args.json_out:
        json_out = _resolve(args.json_out)
        os.makedirs(os.path.dirname(json_out), exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as handle:
            json.dump(card.as_json(), handle, indent=2)
            handle.write("\n")
        print(f"wrote {json_out}")

    print(
        f"{len(card.metrics)} metrics, all cited; {len(card.limitations)} limitations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
