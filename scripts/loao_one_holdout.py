"""Run the baselines and FlowNet for one held-out attacker (used inside the training container).

``run_loao_docker.ps1`` starts one container per holdout and calls this file. It runs the same
two commands as ``run_loao_unsw.ps1``, with the same arguments and the same output paths, so the
run logs are interchangeable with a sequential run.

    python scripts/loao_one_holdout.py <holdout> <data_dir> <runs_dir> <epochs> [--baselines-only]

``--baselines-only`` skips FlowNet. ``run_loao_docker.ps1`` uses it, then runs FlowNet on the host
so it can use the GPU.
"""

from __future__ import annotations

import subprocess
import sys

FILES = 4
USAGE = "usage: loao_one_holdout.py <holdout> <data_dir> <runs_dir> <epochs>"


def main(argv: list[str]) -> int:
    """Run the two steps for one holdout; return the first non-zero exit code."""
    if len(argv) not in (4, 5) or (len(argv) == 5 and argv[4] != "--baselines-only"):
        print(USAGE, file=sys.stderr)
        return 2
    holdout, data_dir, runs_dir, epochs = argv[:4]
    baselines_only = len(argv) == 5

    files: list[str] = []
    for index in range(1, FILES + 1):
        files += ["--file", f"{data_dir}/headered_{index}.csv"]
    common = [
        "--dataset",
        "unsw-nb15",
        *files,
        "--split-policy",
        "leave-one-attacker-out",
        "--holdout-entity",
        holdout,
        "--key",
        "source",
    ]
    steps = [
        [
            sys.executable,
            "scripts/run_baselines.py",
            *common,
            "--out",
            f"{runs_dir}/loao_baselines_{holdout}.json",
        ],
        [
            sys.executable,
            "scripts/train_flownet.py",
            *common,
            "--epochs",
            epochs,
            "--out",
            f"{runs_dir}/loao_flownet_{holdout}.json",
        ],
    ]
    if baselines_only:
        steps = steps[:1]
    for step in steps:
        print("+ " + " ".join(step), flush=True)
        completed = subprocess.run(step, check=False)  # noqa: S603  # nosec B603
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
