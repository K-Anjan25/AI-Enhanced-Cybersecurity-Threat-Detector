#!/usr/bin/env python
r"""Export FlowNet to ONNX and prove the graph is the same model (T-210).

    python scripts/onnx_export.py --out data/runs/flownet.onnx \
        --report data/runs/onnx_export.json

Two numbers are the acceptance criteria, and they answer different questions.

**Agreement.** The exported graph must score a fixed batch within 1e-4 of the
PyTorch model on both heads. This is not a sanity check. The ONNX path exists to
serve the same detector more cheaply, so if the graph disagrees with the weights
it was exported from, the service is quietly running a second model — with
different numbers, under the first one's version label. That is why a wide gap
fails the build rather than logging a warning.

**Latency delta.** Recorded whether or not it favours ONNX. The fallback exists
for the case where PyTorch is too slow; recording only the wins would make this
artifact useless for the decision it is meant to inform. T-209 already measured
the PyTorch path at p95 22.590 ms against a 150 ms budget, so a slower ONNX path
here is a legitimate result and is reported as one.
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
from aegis_ml.serving.onnx_export import (  # noqa: E402
    MAX_ABSOLUTE_DIFFERENCE,
    OnnxScorer,
    TorchScorer,
    export_flow_net,
    load_scorer,
    onnx_available,
)


def _percentile(sorted_values: list[float], q: float) -> float:
    """Nearest-rank percentile of an already-sorted list."""
    if not sorted_values:
        raise ValueError("cannot take a percentile of an empty list")
    index = min(
        len(sorted_values) - 1, max(0, int(round(q * (len(sorted_values) - 1))))
    )
    return sorted_values[index]


def _bench(
    score_fn: object, batch: object, iterations: int, warmup: int
) -> dict[str, float]:
    """Time repeated scoring, discarding warmup."""
    for _ in range(warmup):
        score_fn(batch)
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        score_fn(batch)
        samples.append((time.perf_counter() - start) * 1000.0)
    samples.sort()
    return {
        "p50": _percentile(samples, 0.50),
        "p95": _percentile(samples, 0.95),
        "p99": _percentile(samples, 0.99),
        "fastest": samples[0],
        "slowest": samples[-1],
    }


def main(argv: list[str] | None = None) -> int:
    """Export, compare against PyTorch, and record the latency delta."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="data/runs/flownet.onnx")
    parser.add_argument("--report", default="data/runs/onnx_export.json")
    parser.add_argument("--seed", type=int, default=20260114)
    parser.add_argument("--input-dim", type=int, default=23)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument(
        "--rounds",
        type=int,
        default=5,
        help=(
            "how many times to re-benchmark both backends. A single round cannot "
            "separate a real speedup from machine noise: the same binary on the "
            "same input has been measured with the sign of the difference flipped "
            "between runs, so one number is not a measurement."
        ),
    )
    args = parser.parse_args(argv)

    if not onnx_available():
        print("onnx / onnxruntime are not installed", file=sys.stderr)
        print(
            "this is the documented optional fallback; install ml-service[onnx]",
            file=sys.stderr,
        )
        return 2

    import torch  # noqa: PLC0415
    from aegis_ml.models.flownet import FlowNet, FlowNetConfig  # noqa: PLC0415

    torch.manual_seed(args.seed)
    model = FlowNet(FlowNetConfig(input_dim=args.input_dim))
    model.eval()

    # The comparison batch comes from a seeded generator, so the reported
    # agreement is reproducible and not a function of whatever the global RNG had
    # been left doing.
    generator = torch.Generator().manual_seed(args.seed)
    batch = torch.rand(
        (args.batch, FLOW_WINDOW_SIZE, args.input_dim),
        dtype=torch.float32,
        generator=generator,
    )

    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    artifact = export_flow_net(
        model, out, window_size=FLOW_WINDOW_SIZE, input_dim=args.input_dim
    )
    print(f"exported {artifact} ({artifact.stat().st_size:,} bytes)")

    torch_scorer = TorchScorer(model)
    onnx_scorer = OnnxScorer(artifact)

    reference = torch_scorer.score(batch)
    candidate = onnx_scorer.score(batch)

    diffs = {
        name: float((getattr(reference, name) - getattr(candidate, name)).abs().max())
        for name in ("reconstruction", "anomaly_logits")
    }
    worst = max(diffs.values())
    agrees = worst <= MAX_ABSOLUTE_DIFFERENCE

    # Re-benchmark both backends over several rounds. Each round interleaves them
    # so they see the same machine state, and the spread across rounds is reported
    # alongside the central value -- because a single p95 delta on a shared 2 vCPU
    # box is mostly noise, and a delta whose sign flips between runs is not a
    # result. The fallback question is asked about the tail, not the median: a p50
    # that improves while p95 regresses has not solved the problem it exists for.
    rounds: list[dict[str, dict[str, float]]] = []
    for _ in range(args.rounds):
        rounds.append(
            {
                "torch": _bench(
                    torch_scorer.score, batch, args.iterations, args.warmup
                ),
                "onnx": _bench(onnx_scorer.score, batch, args.iterations, args.warmup),
            }
        )

    def _summary(backend: str, stat: str) -> dict[str, float]:
        values = sorted(r[backend][stat] for r in rounds)
        return {"min": values[0], "median": _percentile(values, 0.5), "max": values[-1]}

    torch_latency = _summary("torch", "p95")
    onnx_latency = _summary("onnx", "p95")
    torch_p50 = _summary("torch", "p50")
    onnx_p50 = _summary("onnx", "p50")

    deltas = sorted(r["onnx"]["p95"] - r["torch"]["p95"] for r in rounds)
    delta_p95 = _percentile(deltas, 0.5)
    favouring_onnx = sum(1 for d in deltas if d < 0)
    # A difference is only a difference if it survives repetition. If the sign
    # flips, the two backends are the same speed at this resolution.
    sign_consistent = favouring_onnx in (0, len(deltas))

    # load_scorer is the production entry point; assert it really does pick ONNX
    # here, otherwise the comparison above says nothing about what serves traffic.
    _, chosen = load_scorer(model, onnx_path=artifact, prefer="onnx")
    _, fallback = load_scorer(model, onnx_path=None, prefer="onnx")

    print(f"fixed batch: {tuple(batch.shape)}  seed {args.seed}")
    print("agreement with the PyTorch model:")
    for name, diff in diffs.items():
        print(f"  {name:16s} max |Δ| {diff:.3e}")
    print(
        f"  worst {worst:.3e} vs tolerance {MAX_ABSOLUTE_DIFFERENCE:.0e}: "
        f"{'PASS' if agrees else 'FAIL - the graph is not this model'}"
    )
    print(
        f"latency over {args.rounds} rounds x {args.iterations} passes of a "
        f"{args.batch}-window batch:"
    )
    print(
        f"  torch p50 {torch_p50['median']:.3f} ms  p95 median {torch_latency['median']:.3f} ms "
        f"(range {torch_latency['min']:.3f}-{torch_latency['max']:.3f})"
    )
    print(
        f"  onnx  p50 {onnx_p50['median']:.3f} ms  p95 median {onnx_latency['median']:.3f} ms "
        f"(range {onnx_latency['min']:.3f}-{onnx_latency['max']:.3f})"
    )
    print(
        f"  p95 delta median {delta_p95:+.3f} ms  "
        f"(range {deltas[0]:+.3f} to {deltas[-1]:+.3f})  "
        f"ONNX faster in {favouring_onnx}/{len(deltas)} rounds"
    )
    if sign_consistent:
        print(
            "  consistent across every round: "
            f"{'ONNX is faster' if delta_p95 < 0 else 'ONNX is slower; PyTorch stays primary'}"
        )
    else:
        print(
            "  sign is not consistent across rounds: the two backends are the same "
            "speed at this resolution, and no single-round delta should be quoted"
        )
    print(f"load_scorer picks {chosen!r} with an artifact, {fallback!r} without")

    fallback_works = chosen == "onnx" and fallback == "torch"

    report_path = (
        args.report if os.path.isabs(args.report) else os.path.join(ROOT, args.report)
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "task": "T-210",
                "artifact": str(artifact),
                "artifact_bytes": artifact.stat().st_size,
                "seed": args.seed,
                "batch_shape": list(batch.shape),
                "agreement": {
                    "max_abs_difference": diffs,
                    "worst": worst,
                    "tolerance": MAX_ABSOLUTE_DIFFERENCE,
                    "passed": agrees,
                },
                "latency_ms": {
                    "rounds": args.rounds,
                    "iterations_per_round": args.iterations,
                    "warmup_discarded": args.warmup,
                    "torch_p95": torch_latency,
                    "onnx_p95": onnx_latency,
                    "torch_p50": torch_p50,
                    "onnx_p50": onnx_p50,
                    "p95_delta_onnx_minus_torch": {
                        "min": deltas[0],
                        "median": delta_p95,
                        "max": deltas[-1],
                        "all": deltas,
                    },
                    "rounds_favouring_onnx": favouring_onnx,
                    "sign_consistent_across_rounds": sign_consistent,
                    "onnx_faster_at_p95": sign_consistent and delta_p95 < 0,
                    "per_round": rounds,
                },
                "fallback": {
                    "backend_with_artifact": chosen,
                    "backend_without_artifact": fallback,
                    "falls_back_to_torch": fallback_works,
                },
                "machine": {
                    "vcpus": os.cpu_count() or 0,
                    "torch_threads": torch.get_num_threads(),
                },
            },
            handle,
            indent=2,
        )
        handle.write("\n")
    print(f"wrote {report_path}")
    return 0 if agrees and fallback_works else 1


if __name__ == "__main__":
    raise SystemExit(main())
