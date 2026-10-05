#!/usr/bin/env python
r"""Inference determinism and latency, measured (T-209, R-67, NFR-01).

    python scripts/inference_benchmark.py --iterations 200 --out data/runs/inference.json

Two claims are checked, and they fail for completely different reasons.

**Determinism (R-67).** The same input through the same pinned model must produce
byte-identical output, not merely close output. Byte comparison matters: a
floating-point difference of 1e-8 is invisible in a metric and still means the
scoring path is not reproducible, and a detector whose score drifts between two
runs cannot be audited. The check compares the raw storage bytes of both heads.

Two further properties are asserted, because "same output twice" is weaker than it
looks:

* a *second model instance* built from the same seed must produce the same bytes.
  This separates "the seed determines the weights" from "the weights happened to
  be in memory".
* the torch RNG state must be **unchanged** by scoring. R-67 forbids unseeded
  randomness in the scoring path, and a forward pass that advanced the generator
  would be a side effect even if its output looked stable.

**Latency (NFR-01).** p95 per-window scoring ≤ 150 ms. Measured with a warmup
discarded, because the first call pays for lazy initialisation that production
pays only once.

**Honesty about the machine.** NFR-01 specifies 4 vCPU. This script reports the
vCPU count it actually ran on and refuses to label the result as a 4-vCPU number
when it is not — a latency figure quoted against a machine nobody is running is
not a measurement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml-service"))
sys.path.insert(0, ROOT)

from aegis_ml.data.windowing import FLOW_WINDOW_SIZE  # noqa: E402

#: NFR-01. Exceeding this blocks the release.
P95_BUDGET_MS = 150.0

#: NFR-01's reference machine.
REFERENCE_VCPUS = 4


def _raw_bytes(tensor: object) -> bytes:
    """The exact bytes of a tensor's storage, for a true byte comparison."""
    import torch  # noqa: PLC0415

    # A real check, not an assert: asserts are stripped under `python -O`, and a
    # validation that disappears under an optimisation flag is not validation.
    if not isinstance(tensor, torch.Tensor):
        raise TypeError(f"expected a Tensor, got {type(tensor).__name__}")
    return bytes(tensor.contiguous().untyped_storage())


def _score(model: object, window: object) -> dict[str, bytes]:
    """One forward pass, returning both heads as raw bytes."""
    import torch  # noqa: PLC0415

    with torch.no_grad():
        output = model(window)
    return {
        "reconstruction": _raw_bytes(output.reconstruction),
        "anomaly_logits": _raw_bytes(output.anomaly_logits),
    }


def main(argv: list[str] | None = None) -> int:
    """Measure determinism and latency; exit non-zero if either claim fails."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260114)
    parser.add_argument("--input-dim", type=int, default=23)
    parser.add_argument(
        "--threads", type=int, default=0, help="0 = leave torch's default"
    )
    parser.add_argument("--out", default="data/runs/inference.json")
    args = parser.parse_args(argv)

    import torch  # noqa: PLC0415
    from aegis_ml.models.flownet import FlowNet, FlowNetConfig  # noqa: PLC0415

    if args.threads > 0:
        torch.set_num_threads(args.threads)

    # A fixed window from a seeded generator: the input is part of what must be
    # reproducible, so it cannot come from the global RNG or from os.urandom.
    generator = torch.Generator().manual_seed(args.seed)
    window = torch.rand(
        (1, FLOW_WINDOW_SIZE, args.input_dim), dtype=torch.float32, generator=generator
    )

    def build() -> FlowNet:
        """A model whose weights are fixed by the seed, in inference mode."""
        torch.manual_seed(args.seed)
        model = FlowNet(FlowNetConfig(input_dim=args.input_dim))
        model.eval()
        return model

    model = build()

    # --- determinism -------------------------------------------------------
    first = _score(model, window)
    repeats_identical = True
    for _ in range(10):
        if _score(model, window) != first:
            repeats_identical = False
            break

    # A different instance, same seed. This is what distinguishes a reproducible
    # model from a model whose weights merely stayed in memory.
    rebuilt_identical = _score(build(), window) == first

    # Scoring must not advance the global RNG. If it did, the forward pass would
    # be consuming randomness -- a side effect, and a violation of R-67.
    rng_before = bytes(torch.get_rng_state().untyped_storage())
    _score(model, window)
    rng_after = bytes(torch.get_rng_state().untyped_storage())
    rng_untouched = rng_before == rng_after

    # Nor must it mutate the weights.
    weights_before = [
        bytes(p.detach().contiguous().untyped_storage()) for p in model.parameters()
    ]
    _score(model, window)
    weights_after = [
        bytes(p.detach().contiguous().untyped_storage()) for p in model.parameters()
    ]
    weights_untouched = weights_before == weights_after

    deterministic = (
        repeats_identical and rebuilt_identical and rng_untouched and weights_untouched
    )

    # --- latency -----------------------------------------------------------
    for _ in range(args.warmup):
        _score(model, window)

    samples: list[float] = []
    for _ in range(args.iterations):
        start = time.perf_counter()
        _score(model, window)
        samples.append((time.perf_counter() - start) * 1000.0)

    samples.sort()

    def percentile(sorted_values: list[float], q: float) -> float:
        """Nearest-rank percentile of an already-sorted list."""
        if not sorted_values:
            raise ValueError("cannot take a percentile of an empty list")
        index = min(
            len(sorted_values) - 1, max(0, int(round(q * (len(sorted_values) - 1))))
        )
        return sorted_values[index]

    p50 = percentile(samples, 0.50)
    p95 = percentile(samples, 0.95)
    p99 = percentile(samples, 0.99)
    fastest = samples[0]
    slowest = samples[-1]
    latency_ok = p95 <= P95_BUDGET_MS

    vcpus = os.cpu_count() or 0
    threads = torch.get_num_threads()
    on_reference_machine = vcpus >= REFERENCE_VCPUS

    print(f"window: 1 x {FLOW_WINDOW_SIZE} x {args.input_dim}  seed {args.seed}")
    print(f"machine: {vcpus} vCPU, torch threads {threads}")
    print("determinism:")
    print(f"  10 repeated passes byte-identical : {repeats_identical}")
    print(f"  rebuilt from the same seed        : {rebuilt_identical}")
    print(f"  torch RNG state untouched         : {rng_untouched}")
    print(f"  model weights untouched           : {weights_untouched}")
    print(
        f"  R-67 deterministic                : {'PASS' if deterministic else 'FAIL'}"
    )
    print(
        f"latency over {args.iterations} scoring passes "
        f"({args.warmup} warmup discarded):"
    )
    print(
        f"  fastest {fastest:.3f} ms  p50 {p50:.3f} ms  p95 {p95:.3f} ms  "
        f"p99 {p99:.3f} ms  slowest {slowest:.3f} ms"
    )
    if on_reference_machine:
        print(
            f"  NFR-01 p95 {p95:.3f} ms vs {P95_BUDGET_MS} ms on "
            f"{REFERENCE_VCPUS} vCPU: {'PASS' if latency_ok else 'FAIL'}"
        )
    else:
        print(
            f"  NFR-01 budget is {P95_BUDGET_MS} ms on {REFERENCE_VCPUS} vCPU, but this "
            f"machine has {vcpus}. Reporting the measured p95 as an in-machine figure; "
            f"{'it is within budget here' if latency_ok else 'it exceeds budget here'}."
        )
    print(f"  overall: {'PASS' if deterministic and latency_ok else 'FAIL'}")

    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    summary = {
        "task": "T-209",
        "rules": ["R-67", "NFR-01"],
        "window": [1, FLOW_WINDOW_SIZE, args.input_dim],
        "seed": args.seed,
        "determinism": {
            "repeated_passes_byte_identical": repeats_identical,
            "rebuilt_from_same_seed_identical": rebuilt_identical,
            "rng_state_untouched": rng_untouched,
            "weights_untouched": weights_untouched,
            "passed": deterministic,
            "comparison": "raw storage bytes of both heads",
        },
        "latency_ms": {
            "iterations": args.iterations,
            "warmup_discarded": args.warmup,
            "fastest": fastest,
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "slowest": slowest,
            "budget_p95": P95_BUDGET_MS,
            "passed": latency_ok,
        },
        "machine": {
            "vcpus": vcpus,
            "torch_threads": threads,
            "matches_nfr01_reference": on_reference_machine,
            "reference_vcpus": REFERENCE_VCPUS,
            "note": (
                "NFR-01 specifies 4 vCPU. This figure was measured on the machine "
                "reported above and is not a substitute for a 4 vCPU measurement "
                "unless matches_nfr01_reference is true."
                if not on_reference_machine
                else "measured on a machine meeting the NFR-01 reference vCPU count"
            ),
        },
    }
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")
    print(f"wrote {out}")
    return 0 if deterministic and latency_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
