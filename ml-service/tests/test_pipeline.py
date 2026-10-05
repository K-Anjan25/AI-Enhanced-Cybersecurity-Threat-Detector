"""Tests for :mod:`aegis_ml.training.pipeline` (T-202).

Split in two on purpose. Everything that does not need torch runs in CI, so the
manifest and config contracts are checked on every commit. The training and
resume tests need the ``ml-service[training]`` extra and skip without it — which
means the ±0.005 AUC acceptance clause is verified locally and recorded, not
enforced by CI. That gap is stated rather than hidden.
"""

from __future__ import annotations

import json
import re

import pytest
from aegis_ml.training.pipeline import (
    Checkpoint,
    DatasetDigest,
    RunManifest,
    TrainingConfig,
    git_state,
    seed_map,
)


def manifest(**overrides: object) -> RunManifest:
    """A valid manifest, for the tests that only care about one field."""
    base: dict[str, object] = {
        "model_id": "flownet-v0.1.0",
        "git_sha": "a" * 40,
        "git_dirty": False,
        "config": TrainingConfig(),
        "seeds": seed_map(20260114),
        "datasets": (DatasetDigest(name="friday.csv", sha256="b" * 64, bytes=36010816),),
        "metrics": {"roc_auc": 0.8053},
    }
    base.update(overrides)
    return RunManifest.model_validate(base)


# --- dataset digests -------------------------------------------------------


def test_digest_matches_an_independent_hash(tmp_path: object) -> None:
    """The hash must be the file's, computed the same way any other tool would."""
    import hashlib
    import os

    path = os.path.join(str(tmp_path), "capture.csv")  # noqa: PTH118
    with open(path, "wb") as handle:
        handle.write(b"header\n1,2,3\n" * 1000)

    with open(path, "rb") as handle:
        expected = hashlib.sha256(handle.read()).hexdigest()
    digest = DatasetDigest.of(path)

    assert digest.sha256 == expected
    assert digest.bytes == os.path.getsize(path)
    assert digest.name == "capture.csv"


def test_digest_rejects_a_malformed_hash() -> None:
    with pytest.raises(ValueError, match="sha256"):
        DatasetDigest(name="x", sha256="not-a-hash", bytes=1)


# --- the manifest contract -------------------------------------------------


def test_manifest_round_trip_is_lossless() -> None:
    original = manifest()

    assert RunManifest.model_validate_json(original.model_dump_json()) == original


def test_identical_runs_produce_identical_manifest_bytes(tmp_path: object) -> None:
    """The point of leaving the clock out.

    If the manifest carried a timestamp, "two runs agree" could only ever be
    checked against the metrics and never against the artifacts.
    """
    import os

    first = os.path.join(str(tmp_path), "a.json")  # noqa: PTH118
    second = os.path.join(str(tmp_path), "b.json")  # noqa: PTH118
    manifest().save(first)
    manifest().save(second)

    with open(first, encoding="utf-8") as one, open(second, encoding="utf-8") as two:
        assert one.read() == two.read()


def test_manifest_has_no_timestamp_field() -> None:
    """Guard the property above against a well-meaning later addition."""
    payload = manifest().model_dump_json()

    assert "timestamp" not in payload
    assert "created" not in payload
    assert not re.search(r"\d{4}-\d{2}-\d{2}", payload)


def test_manifest_carries_what_t202_requires() -> None:
    """The acceptance criterion names four contents; assert all four are present."""
    built = manifest()
    payload = json.loads(built.model_dump_json())

    assert payload["datasets"][0]["sha256"]  # dataset hashes
    assert payload["git_sha"]  # git SHA
    assert payload["config"]["learning_rate"]  # config
    assert payload["seeds"]["root"]  # seeds
    assert payload["metrics"]["roc_auc"]  # metrics


def test_manifest_rejects_an_untracked_field() -> None:
    """extra=forbid, so a new knob cannot enter a run without entering the schema."""
    with pytest.raises(ValueError, match="extra"):
        RunManifest.model_validate({**json.loads(manifest().model_dump_json()), "surprise": 1})


def test_git_state_reports_a_sha_and_whether_the_tree_is_dirty() -> None:
    sha, dirty = git_state()

    assert sha == "unknown" or re.fullmatch(r"[0-9a-f]{40}", sha)
    assert isinstance(dirty, bool)


# --- seeds -----------------------------------------------------------------


def test_seeds_are_derived_not_repeated() -> None:
    """Roles sharing one literal produce correlated streams."""
    seeds = seed_map(20260114)

    assert len(set(seeds.values())) == len(seeds)
    assert seeds["root"] == 20260114


def test_seeds_are_a_pure_function_of_the_root() -> None:
    assert seed_map(7) == seed_map(7)
    assert seed_map(7) != seed_map(8)


# --- config ----------------------------------------------------------------


def test_config_rejects_an_untracked_knob() -> None:
    with pytest.raises(ValueError, match="extra"):
        TrainingConfig.model_validate({"learning_rate": 0.1, "warmup_steps": 10})


def test_config_rejects_unusable_values() -> None:
    with pytest.raises(ValueError, match="epochs"):
        TrainingConfig(epochs=0)
    with pytest.raises(ValueError, match="learning_rate"):
        TrainingConfig(learning_rate=0.0)
    with pytest.raises(ValueError, match="dropout"):
        TrainingConfig(dropout=1.0)


def test_checkpoint_digest_changes_with_the_config() -> None:
    """So a resume against edited settings is refused rather than silently mixed."""
    base = Checkpoint.config_digest_of(TrainingConfig())

    assert base == Checkpoint.config_digest_of(TrainingConfig())
    assert base != Checkpoint.config_digest_of(TrainingConfig(learning_rate=3e-4))


# --- training and resume (needs the training extra) ------------------------

torch = pytest.importorskip("torch", reason="torch is the ml-service[training] extra")

from aegis_ml.training.pipeline import load_checkpoint, train  # noqa: E402


def sample(n: int = 24, seq: int = 12, width: int = 8) -> tuple[list[list[list[float]]], list[int]]:
    """A small deterministic training set."""
    generator = torch.Generator().manual_seed(5)
    x = torch.rand(n, seq, width, generator=generator).tolist()
    y = [int(i % 3 == 0) for i in range(n)]
    return x, y


def test_two_runs_of_one_config_are_bitwise_identical() -> None:
    """Stronger than the ±0.005 AUC clause, and the reason that clause holds."""
    x, y = sample()
    config = TrainingConfig(epochs=2, dropout=0.0)

    first, first_losses = train(config, x, y)
    second, second_losses = train(config, x, y)

    assert first_losses == second_losses
    for a, b in zip(first.state_dict().values(), second.state_dict().values(), strict=True):
        assert torch.equal(a, b)


def test_different_seeds_give_different_models() -> None:
    """So the test above cannot pass because seeding is a no-op."""
    x, y = sample()

    first, _ = train(TrainingConfig(epochs=1, dropout=0.0, seed=1), x, y)
    second, _ = train(TrainingConfig(epochs=1, dropout=0.0, seed=2), x, y)

    differs = any(
        not torch.equal(a, b)
        for a, b in zip(first.state_dict().values(), second.state_dict().values(), strict=True)
    )
    assert differs


def test_a_checkpoint_round_trip_preserves_weights_exactly(tmp_path: object) -> None:
    """Save at the last epoch, load it back, and require bit-identical weights.

    This checks the serialisation, not the training: with ``epochs_completed``
    already at the configured total there is nothing left to run, so any
    difference is the round trip's fault. The shuffle-order property is tested
    separately below, where it can actually fail.
    """
    import os

    x, y = sample()
    config = TrainingConfig(epochs=4, dropout=0.0)
    directory = os.path.join(str(tmp_path), "ckpt")  # noqa: PTH118

    interrupted, interrupted_losses = train(config, x, y, checkpoint_dir=directory)
    # Rewind to the state saved after epoch 2 and finish from there.
    checkpoint, state = load_checkpoint(directory, config)
    assert checkpoint.epochs_completed == 4
    resumed, resumed_losses = train(config, x, y, resume_from=directory, on_epoch=None)

    assert interrupted_losses == resumed_losses
    for a, b in zip(interrupted.state_dict().values(), resumed.state_dict().values(), strict=True):
        assert torch.equal(a, b)
    assert state is not None


def test_a_partially_trained_resume_matches_the_uninterrupted_run(tmp_path: object) -> None:
    """Stop early, resume, and land where an uninterrupted run would have."""
    import os

    x, y = sample()
    directory = os.path.join(str(tmp_path), "ckpt")  # noqa: PTH118

    config = TrainingConfig(epochs=4, dropout=0.0)
    full, full_losses = train(config, x, y)

    def interrupt(epoch: int, loss: float) -> None:
        if epoch == 2:
            raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError, match="simulated interruption"):
        train(config, x, y, checkpoint_dir=directory, on_epoch=interrupt)
    # The checkpoint written for epoch 2 survived the failure, which is the
    # reason the write happens before the callback.
    partial, partial_losses = train(config, x, y, resume_from=directory)

    assert len(partial_losses) == 4
    assert list(full_losses[2:]) == list(partial_losses[2:])
    for a, b in zip(full.state_dict().values(), partial.state_dict().values(), strict=True):
        assert torch.equal(a, b)


def test_resuming_under_a_changed_config_is_refused(tmp_path: object) -> None:
    import os

    x, y = sample()
    directory = os.path.join(str(tmp_path), "ckpt")  # noqa: PTH118
    train(TrainingConfig(epochs=1, dropout=0.0), x, y, checkpoint_dir=directory)

    with pytest.raises(ValueError, match="different config"):
        train(
            TrainingConfig(epochs=2, dropout=0.0, learning_rate=3e-4),
            x,
            y,
            resume_from=directory,
        )


def test_training_input_is_validated() -> None:
    x, y = sample()

    with pytest.raises(ValueError, match="labels"):
        train(TrainingConfig(epochs=1), x, y[:-1])
    with pytest.raises(ValueError, match="zero windows"):
        train(TrainingConfig(epochs=1), [], [])
