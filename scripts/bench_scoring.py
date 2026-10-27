#!/usr/bin/env python3
"""Time one window through the real FlowNet scorer (NFR-01, in-process latency).

Times ``FlowNetScorer.score()`` on 50-flow windows: encoding, the model forward pass,
and the explanation. That is the call the scoring path makes per window.

The weights are randomly initialised, so the numbers are a latency measurement, not a
model-quality one. Latency depends on the architecture and the input shape, not on
what the weights learned. The output says so, and it records the CPU it ran on.

Usage (needs the ml-service torch extra):
    python scripts/bench_scoring.py --windows 300
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time

import torch
from aegis_ml.data.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, extract_flow_window
from aegis_ml.data.preprocess import Preprocessor, StandardScaler, Vocabulary
from aegis_ml.data.synthetic import generate_dataset
from aegis_ml.data.windowing import WindowKey, window_flows
from aegis_ml.models.flownet import FlowNet, FlowNetConfig
from aegis_ml.serving.flownet_scorer import FlowNetScorer, feature_names

WINDOW = 50


def main() -> None:
    """Build a random-weight FlowNet scorer and time it over synthetic windows."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--windows", type=int, default=300)
    args = parser.parse_args()

    records = sorted(generate_dataset(per_scenario=400, seed=7).flows, key=lambda r: r.timestamp)
    windows = window_flows(records, key=WindowKey.SOURCE)
    rows = []
    for window in windows:
        rows.extend(extract_flow_window(window.records, key=WindowKey.SOURCE))
    scaler = StandardScaler.fit([list(r.numeric) for r in rows], NUMERIC_FEATURES)
    vocabularies = {
        name: Vocabulary.fit(r.categorical[index] for r in rows)
        for index, name in enumerate(CATEGORICAL_FEATURES)
    }
    preprocessor = Preprocessor(scaler=scaler, vocabularies=vocabularies)

    torch.manual_seed(0)
    model = FlowNet(FlowNetConfig(input_dim=len(feature_names(preprocessor))))
    model.eval()
    scorer = FlowNetScorer(
        model,
        preprocessor,
        model_id="latency-probe-random-init",
        window_size=WINDOW,
        window_key=WindowKey.SOURCE,
        sha256="random-init",
    )

    pool = [w.records[:WINDOW] for w in windows if len(w.records) >= WINDOW]
    if not pool:
        raise SystemExit("synthetic data produced no full 50-flow window")
    for window in pool[:10]:  # warm-up, not timed
        scorer.score(window)

    timings_ms = []
    for index in range(args.windows):
        window = pool[index % len(pool)]
        started = time.perf_counter()
        scorer.score(window)
        timings_ms.append((time.perf_counter() - started) * 1000)

    timings_ms.sort()

    def pct(p: float) -> float:
        return timings_ms[min(len(timings_ms) - 1, int(round(p / 100 * len(timings_ms))) - 1)]

    print(
        json.dumps(
            {
                "measures": "FlowNetScorer.score() per 50-flow window, in process",
                "weights": "random init (latency only; not a model-quality result)",
                "windows_timed": len(timings_ms),
                "p50_ms": round(pct(50), 2),
                "p95_ms": round(pct(95), 2),
                "p99_ms": round(pct(99), 2),
                "mean_ms": round(statistics.fmean(timings_ms), 2),
                "torch": torch.__version__,
                "torch_threads": torch.get_num_threads(),
                "cpu_count": os.cpu_count(),
                "machine": platform.machine(),
                "nfr01_reference": "p95 <= 150 ms per window on 4 vCPU",
            }
        )
    )


if __name__ == "__main__":
    main()
