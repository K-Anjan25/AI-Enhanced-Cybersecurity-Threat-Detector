"""Tests for :mod:`aegis_ml.models.flownet` (T-201).

The whole module is skipped when torch is absent, because torch is an optional
extra: the service must still install and test without it.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch", reason="torch is the ml-service[training] extra")

from aegis_ml.data.features import FEATURE_NAMES  # noqa: E402
from aegis_ml.models.flownet import (  # noqa: E402
    ENCODER_LAYERS,
    FlowNet,
    FlowNetConfig,
    parameter_count,
    reconstruction_error,
)


def batch(size: int = 4, seq: int = 50) -> torch.Tensor:
    """A deterministic pseudo-random batch of windows."""
    generator = torch.Generator().manual_seed(1234)
    return torch.rand(size, seq, len(FEATURE_NAMES), generator=generator)


# --- shape and size --------------------------------------------------------


def test_forward_returns_both_heads_with_the_documented_shapes() -> None:
    output = FlowNet()(batch(size=4, seq=50))

    assert tuple(output.reconstruction.shape) == (4, 50, len(FEATURE_NAMES))
    assert tuple(output.anomaly_logits.shape) == (4,)


def test_encoder_depth_is_the_specified_four_layers() -> None:
    assert ENCODER_LAYERS == 4
    assert len(FlowNet().encoder.layers) == ENCODER_LAYERS


def test_parameter_count_is_recorded() -> None:
    """T-201's acceptance criterion names the count, so it is pinned.

    If this number moves, the architecture moved with it, and that is a model
    identity change rather than a refactor.
    """
    assert parameter_count(FlowNet()) == 139_160


def test_shorter_windows_are_accepted() -> None:
    """Windows close on inactivity as well as on count, so length varies."""
    output = FlowNet()(batch(size=2, seq=7))

    assert tuple(output.reconstruction.shape) == (2, 7, len(FEATURE_NAMES))


# --- determinism (R-67) ----------------------------------------------------


def test_identical_seeds_produce_identical_outputs() -> None:
    x = batch()

    torch.manual_seed(99)
    first = FlowNet()(x)
    torch.manual_seed(99)
    second = FlowNet()(x)

    assert torch.equal(first.reconstruction, second.reconstruction)
    assert torch.equal(first.anomaly_logits, second.anomaly_logits)


def test_different_seeds_produce_different_weights() -> None:
    """Guards the determinism test above against passing for a trivial reason."""
    x = batch()

    torch.manual_seed(1)
    first = FlowNet()(x)
    torch.manual_seed(2)
    second = FlowNet()(x)

    assert not torch.equal(first.reconstruction, second.reconstruction)


def test_eval_mode_is_deterministic_across_calls() -> None:
    """Dropout must be off at inference, or scoring is not reproducible."""
    model = FlowNet().eval()
    x = batch()

    with torch.no_grad():
        assert torch.equal(model(x).reconstruction, model(x).reconstruction)


# --- it actually learns ----------------------------------------------------


def test_the_reconstruction_head_can_fit_a_single_batch() -> None:
    """A model that cannot overfit one batch has a broken gradient path.

    This is the test that distinguishes a wired-up architecture from a plausible
    looking one: shape checks pass either way.
    """
    torch.manual_seed(7)
    model = FlowNet(FlowNetConfig(dropout=0.0)).train()
    x = batch(size=8, seq=20)
    optimiser = torch.optim.Adam(model.parameters(), lr=1e-2)

    first = reconstruction_error(model(x), x).item()
    for _ in range(150):
        optimiser.zero_grad()
        loss = reconstruction_error(model(x), x)
        loss.backward()
        optimiser.step()
    last = reconstruction_error(model(x), x).item()

    # Measured, not assumed: 150 steps at lr 1e-2 take this batch from 0.509 to
    # 0.077, a 6.7x fall. The bar is set at 4x so it still fails on a broken
    # gradient path without asserting a margin that was never observed.
    assert last < first / 4, f"loss only fell from {first:.4f} to {last:.4f}"


def test_gradients_reach_every_parameter() -> None:
    """No dead head: both outputs must contribute to the loss."""
    torch.manual_seed(11)
    model = FlowNet().train()
    x = batch(size=2, seq=12)
    output = model(x)
    (reconstruction_error(output, x) + output.anomaly_logits.square().mean()).backward()

    starved = [name for name, p in model.named_parameters() if p.grad is None or not p.grad.any()]
    assert not starved, f"no gradient reached: {starved}"


# --- validation ------------------------------------------------------------


def test_wrong_tensor_shapes_are_rejected() -> None:
    model = FlowNet()

    with pytest.raises(ValueError, match=r"expected \(batch, seq"):
        model(torch.zeros(4, len(FEATURE_NAMES)))
    with pytest.raises(ValueError, match="features per timestep"):
        model(torch.zeros(4, 50, len(FEATURE_NAMES) + 1))


def test_sequences_longer_than_the_positional_encoding_are_rejected() -> None:
    model = FlowNet(FlowNetConfig(max_seq_len=10))

    with pytest.raises(ValueError, match="exceeds max_seq_len"):
        model(torch.zeros(1, 11, len(FEATURE_NAMES)))


def test_config_rejects_unusable_shapes() -> None:
    with pytest.raises(ValueError, match="divisible by nhead"):
        FlowNetConfig(d_model=65, nhead=8)
    with pytest.raises(ValueError, match="dropout"):
        FlowNetConfig(dropout=1.0)
    with pytest.raises(ValueError, match="input_dim"):
        FlowNetConfig(input_dim=0)
    with pytest.raises(ValueError, match="max_seq_len"):
        FlowNetConfig(max_seq_len=0)
