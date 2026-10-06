#!/usr/bin/env python3
"""Render the API reference from the application's Pydantic schemas (T-320).

The reference is generated, never hand-written: it is a rendering of the same
`/openapi.json` FastAPI derives from the route decorators and the Pydantic
response models in `backend/app/schemas/`. Two things keep it honest:

  * every operation has to clear the coverage rule in `app.api.openapi_docs`
    (summary, success schema or declared media type, a documented body for every
    body method, resolving `$ref`s) -- the rule is documented in D-054 and its
    tests fail a route that skips one; and
  * CI runs this script with `--check`, which renders the document again and
    fails when the committed file differs, so a route or a field cannot change
    without the reference changing in the same commit.

Usage:
    python scripts/generate_api_reference.py            # rewrite the file
    python scripts/generate_api_reference.py --check     # fail on drift
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
OUTPUT = os.path.join(ROOT, "api-reference.md")


def render() -> str:
    """Build the app the way the tests do and render its reference."""
    sys.path.insert(0, BACKEND)
    from app.api.openapi_docs import documentation_problems, render_reference
    from app.core.config import Environment, Settings
    from app.main import create_app

    app = create_app(
        Settings(
            env=Environment.TEST,
            # Throwaway value for static rendering only. It never serves traffic
            # and is not a credential (R-50).
            secret_key="K7qzR2mVx9pL4tYbN6wJ8sDfG1hA3cEu",  # noqa: S106  # pragma: allowlist secret
        )
    )
    problems = documentation_problems(app)
    if problems:
        raise SystemExit(
            "the application's own documentation is incomplete, so no reference "
            "was rendered:\n  - " + "\n  - ".join(problems)
        )
    return render_reference(app)


def main(argv: list[str] | None = None) -> int:
    """Write the reference, or check the committed one against a fresh render."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed reference differs from a fresh render",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT,
        help=f"file to write (default: {os.path.relpath(OUTPUT, ROOT)})",
    )
    args = parser.parse_args(argv)

    rendered = render()
    if args.check:
        try:
            with open(args.output, encoding="utf-8") as handle:
                committed = handle.read()
        except FileNotFoundError:
            print(
                f"{os.path.relpath(args.output, ROOT)} is missing; run "
                "scripts/generate_api_reference.py",
                file=sys.stderr,
            )
            return 1
        if committed != rendered:
            print(
                f"{os.path.relpath(args.output, ROOT)} is stale; run "
                "scripts/generate_api_reference.py to rewrite it",
                file=sys.stderr,
            )
            return 1
        print(f"{os.path.relpath(args.output, ROOT)} is up to date")
        return 0

    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(rendered)
    print(
        f"wrote {os.path.relpath(args.output, ROOT)} ({len(rendered.splitlines())} lines)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
