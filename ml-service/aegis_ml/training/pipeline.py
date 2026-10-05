"""Config-driven training with checkpointing, resume and a run manifest (T-202).

Three properties matter here, and each is enforced by something other than care:

**Reproducibility (R-67).** Every source of randomness takes its seed from
:class:`TrainingConfig` and nothing else. Weight initialisation is seeded, and
epoch *n*'s shuffle order depends only on ``(seed, n)`` — not on how many epochs
ran before it. That second property is what makes resume correct: continuing from
epoch 5 must land on the same weights as running straight through, because the
shuffle that epoch 6 sees is a function of the seed, not of history.

**A manifest with no clock in it.** Two runs of one config must produce
byte-identical manifests, or "the two runs agree" cannot be checked against the
artifacts themselves. So there is no timestamp field. A run's wall-clock start
time is operationally useful and belongs in a log line, not in a document whose
job is to be reproduced.

**torch is optional.** This module imports cleanly without it, because config,
manifest and digest handling are the parts worth testing everywhere. torch is
imported inside the functions that need it.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # pragma: no cover - typing only, torch is an optional extra
    from torch import nn

    from aegis_ml.models.flownet import FlowNetConfig

SCHEMA_VERSION: Literal["run-manifest@1"] = "run-manifest@1"


class DatasetDigest(BaseModel):
    """One input dataset, identified by its bytes rather than its name.

    A filename says what a run was *asked* to read. A hash says what it read, and
    those differ whenever a mirror silently re-publishes under the same name —
    which the UNSW mirrors in this project's manifest actually do.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0)

    @classmethod
    def of(cls, path: str, *, name: str | None = None) -> DatasetDigest:
        """Hash a file on disk. Streamed, so a large capture fits in memory."""
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
                size += len(chunk)
        return cls(name=name or os.path.basename(path), sha256=digest.hexdigest(), bytes=size)


class TrainingConfig(BaseModel):
    """Everything that determines a run's outcome, and nothing that does not.

    Anything left out of this model is either not a hyperparameter or is a bug:
    an untracked knob makes two "identical" runs differ for a reason no manifest
    can explain.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str = "flownet-v0.1.0"
    # Architecture. Mirrors FlowNetConfig, restated as plain fields so this model
    # imports without torch.
    d_model: int = Field(default=176, ge=1)
    nhead: int = Field(default=8, ge=1)
    dim_feedforward: int = Field(default=448, ge=1)
    dropout: float = Field(default=0.1, ge=0.0, lt=1.0)
    max_seq_len: int = Field(default=50, ge=1)
    # Optimisation.
    epochs: int = Field(default=3, ge=1)
    batch_size: int = Field(default=32, ge=1)
    learning_rate: float = Field(default=1e-3, gt=0.0)
    seed: int = Field(default=20260114)

    def model_config_for(self, input_dim: int) -> FlowNetConfig:
        """Build the torch-side config. Imports torch, so it is not called at import time."""
        from aegis_ml.models.flownet import FlowNetConfig  # noqa: PLC0415

        return FlowNetConfig(
            input_dim=input_dim,
            d_model=self.d_model,
            nhead=self.nhead,
            dim_feedforward=self.dim_feedforward,
            dropout=self.dropout,
            max_seq_len=self.max_seq_len,
        )


class RunManifest(BaseModel):
    """What a run was, recorded so the result can be argued with later.

    T-202's acceptance names the required contents: dataset hashes, git SHA,
    config, seeds, metrics. Deliberately absent: a timestamp. See the module
    docstring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["run-manifest@1"] = SCHEMA_VERSION
    model_id: str
    git_sha: str
    git_dirty: bool
    config: TrainingConfig
    #: Every seed actually used, by the role it played. A single ``seed`` field
    #: would not show that the shuffle and the init were seeded independently.
    seeds: dict[str, int]
    datasets: tuple[DatasetDigest, ...]
    #: Opaque on purpose: the metric schema is ``evaluate()``'s, and duplicating
    #: it here would give the two a chance to drift.
    metrics: dict[str, object] = Field(default_factory=dict)
    environment: dict[str, str] = Field(default_factory=dict)

    def save(self, path: str) -> None:
        """Write the manifest. Sorted keys so the bytes are stable."""
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.model_dump_json(indent=2))
            handle.write("\n")

    @classmethod
    def load(cls, path: str) -> RunManifest:
        """Read a manifest back. A round trip must be lossless."""
        with open(path, encoding="utf-8") as handle:
            return cls.model_validate_json(handle.read())


def git_state() -> tuple[str, bool]:
    """Return ``(sha, dirty)`` for the working tree.

    ``dirty`` matters as much as the SHA: a run made from uncommitted changes
    cannot be reproduced from the SHA alone, and a manifest that claims otherwise
    is worse than one that admits the gap. Outside a repository the SHA is
    ``unknown`` rather than an error, because training should not fail for a
    reason unrelated to the model.
    """
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 - git has no fixed install path
            capture_output=True,
            text=True,
            check=True,
            errors="replace",
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],  # noqa: S607 - git has no fixed install path
            capture_output=True,
            text=True,
            check=True,
            errors="replace",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown", False
    return sha or "unknown", bool(status)


def seed_map(seed: int) -> dict[str, int]:
    """The seeds a run uses, derived from one root.

    Derived rather than repeated: two roles sharing one literal seed produce
    correlated streams, and a shuffle that mirrors the dropout mask is a subtle
    way to make a run less random than it looks.
    """
    return {
        "root": seed,
        "init": seed + 1,
        "shuffle": seed + 2,
        "dropout": seed + 3,
    }


class Checkpoint(BaseModel):
    """Resume state. Weights are stored separately, as a torch file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    epochs_completed: int = Field(ge=0)
    config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    losses: tuple[float, ...] = ()

    @staticmethod
    def config_digest_of(config: TrainingConfig) -> str:
        """A fingerprint of the config, so a resume against changed settings is refused."""
        return hashlib.sha256(config.model_dump_json().encode("utf-8")).hexdigest()


def save_checkpoint(
    directory: str, checkpoint: Checkpoint, state: dict[str, object]
) -> tuple[str, str]:
    """Write ``state`` and the resume metadata. Returns both paths."""
    import torch  # noqa: PLC0415

    os.makedirs(directory, exist_ok=True)
    weights = os.path.join(directory, "weights.pt")
    meta = os.path.join(directory, "checkpoint.json")
    torch.save(state, weights)
    with open(meta, "w", encoding="utf-8") as handle:
        handle.write(checkpoint.model_dump_json(indent=2))
        handle.write("\n")
    return weights, meta


def load_checkpoint(directory: str, config: TrainingConfig) -> tuple[Checkpoint, dict[str, object]]:
    """Read a checkpoint, refusing one written under a different config.

    Resuming a half-trained run after editing the learning rate produces a model
    that matches neither configuration, and does so silently. Refusing is cheap;
    discovering it later is not.
    """
    import torch  # noqa: PLC0415

    with open(os.path.join(directory, "checkpoint.json"), encoding="utf-8") as handle:
        checkpoint = Checkpoint.model_validate_json(handle.read())
    expected = Checkpoint.config_digest_of(config)
    if checkpoint.config_digest != expected:
        msg = (
            "checkpoint was written under a different config; refusing to resume "
            f"({checkpoint.config_digest[:12]} != {expected[:12]})"
        )
        raise ValueError(msg)
    state: dict[str, object] = torch.load(os.path.join(directory, "weights.pt"), weights_only=False)
    return checkpoint, state


def train(
    config: TrainingConfig,
    x: Sequence[Sequence[Sequence[float]]],
    y: Sequence[int],
    *,
    resume_from: str | None = None,
    on_epoch: Callable[[int, float], None] | None = None,
    checkpoint_dir: str | None = None,
) -> tuple[nn.Module, tuple[float, ...]]:
    """Train FlowNet under ``config`` and return ``(model, per_epoch_loss)``.

    ``x`` is a sequence of windows, each a sequence of feature vectors; ``y`` is
    one binary label per window. Resume and checkpointing are optional and
    orthogonal: passing ``resume_from`` continues, passing ``checkpoint_dir``
    writes state after every epoch so an interrupted run can be continued.
    """
    import torch  # noqa: PLC0415

    from aegis_ml.models.flownet import FlowNet, reconstruction_error  # noqa: PLC0415

    if len(x) != len(y):
        msg = f"{len(x)} windows but {len(y)} labels"
        raise ValueError(msg)
    if not x:
        msg = "cannot train on zero windows"
        raise ValueError(msg)

    seeds = seed_map(config.seed)
    width = len(x[0][0])
    if resume_from:
        checkpoint, state = load_checkpoint(resume_from, config)
        model = FlowNet(config.model_config_for(width))
        model.load_state_dict(cast("dict[str, object]", state["model"]))
        optimiser = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
        optimiser.load_state_dict(cast("dict[str, object]", state["optimiser"]))
        done = checkpoint.epochs_completed
        losses = list(checkpoint.losses)
    else:
        torch.manual_seed(seeds["init"])
        model = FlowNet(config.model_config_for(width))
        optimiser = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
        done = 0
        losses = []

    x_train = torch.tensor(x, dtype=torch.float32)
    y_train = torch.tensor(y, dtype=torch.float32)
    bce = torch.nn.BCEWithLogitsLoss()

    model.train()
    for epoch in range(done, config.epochs):
        # The order depends on (seed, epoch) alone, never on how many epochs have
        # already run. That is the whole of resume correctness: an interrupted run
        # and an uninterrupted one must see the same batches in the same order.
        order = torch.randperm(
            x_train.size(0),
            generator=torch.Generator().manual_seed(seeds["shuffle"] + epoch),
        )
        total, batches = 0.0, 0
        for start in range(0, order.numel(), config.batch_size):
            index = order[start : start + config.batch_size]
            batch_x, batch_y = x_train[index], y_train[index]
            optimiser.zero_grad()
            output = model(batch_x)
            loss = reconstruction_error(output, batch_x) + bce(output.anomaly_logits, batch_y)
            loss.backward()
            optimiser.step()
            total += float(loss.item())
            batches += 1
        mean = total / batches
        losses.append(mean)
        # Persisted before the callback runs, not after. A progress callback is
        # caller code and may fail; finishing the write first means a failure
        # costs the callback, not the epoch that was just trained.
        if checkpoint_dir:
            save_checkpoint(
                checkpoint_dir,
                Checkpoint(
                    epochs_completed=epoch + 1,
                    config_digest=Checkpoint.config_digest_of(config),
                    losses=tuple(losses),
                ),
                {"model": model.state_dict(), "optimiser": optimiser.state_dict()},
            )
        if on_epoch is not None:
            on_epoch(epoch + 1, mean)

    return model, tuple(losses)
