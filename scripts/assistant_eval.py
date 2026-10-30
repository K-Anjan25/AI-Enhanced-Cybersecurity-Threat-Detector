r"""Run the assistant evaluation set against a live AEGIS server and report the pass rate.

    PYTHONPATH=backend python scripts/assistant_eval.py \\
        --base-url http://localhost:8000 \\
        --email admin@aegis.local --password "<your password>" --min-pass 0.9

A case passes when the server's answer came from the expected tool (or none, for a
refusal or help), and when a refusal is refused by the guardrail, not answered by a
model. Run it with PYTHONPATH=backend so the eval set imports. Pass rate and latency are
printed, one line per case. Exit status is 1 below --min-pass, so this can gate a model
change.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

from app.services.assistant.eval_set import EVAL_CASES  # type: ignore[import-not-found]


def _sign_in(base: str, email: str, password: str) -> str:
    body = json.dumps({"email": email, "password": password}).encode()
    request = urllib.request.Request(  # noqa: S310 - operator-supplied URL
        f"{base}/api/v1/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310  # nosec B310
        token: str = json.loads(response.read())["access_token"]
        return token


def _ask(base: str, token: str, question: str) -> dict[str, object]:
    query = urllib.parse.urlencode({"question": question})
    request = urllib.request.Request(  # noqa: S310 - operator-supplied URL
        f"{base}/api/v1/assistant/ask?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310  # nosec B310
        parsed: dict[str, object] = json.loads(response.read())
        return parsed


def main(argv: list[str] | None = None) -> int:
    """Run every case, print each result, and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--min-pass", type=float, default=0.9)
    args = parser.parse_args(argv)

    base = args.base_url.rstrip("/")
    token = _sign_in(base, args.email, args.password)
    passed = 0
    for case in EVAL_CASES:
        started = time.perf_counter()
        reply = _ask(base, token, case.question)
        elapsed = time.perf_counter() - started
        sources = list(reply.get("sources", []))  # type: ignore[call-overload]
        backend = str(reply.get("backend", ""))
        if case.source is None:
            ok = backend in ("guardrail", "rules")
            if case.intent.startswith("refuse"):
                ok = backend == "guardrail"
        else:
            ok = case.source in sources and backend in ("rules", "openai")
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"{mark} {elapsed:5.2f}s [{backend}] {case.question}")
    rate = passed / len(EVAL_CASES)
    print(f"\n{passed}/{len(EVAL_CASES)} passed ({rate:.0%}); threshold {args.min_pass:.0%}")
    return 0 if rate >= args.min_pass else 1


if __name__ == "__main__":
    sys.exit(main())
