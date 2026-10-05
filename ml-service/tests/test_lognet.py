"""Tests for :mod:`aegis_ml.models.lognet` and T-204's mining stability clause."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch", reason="torch is the ml-service[training] extra")

from aegis_ml.models.lognet import (  # noqa: E402
    ENCODER_LAYERS,
    LogNet,
    LogNetConfig,
    hypersphere_loss,
    masked_template_loss,
    parameter_count,
)


def tokens(batch: int = 4, seq: int = 40, vocab: int = 64) -> torch.Tensor:
    """A deterministic batch of template-id windows."""
    generator = torch.Generator().manual_seed(99)
    return torch.randint(1, vocab, (batch, seq), generator=generator)


# --- shape and depth -------------------------------------------------------


def test_forward_returns_the_documented_shapes() -> None:
    output = LogNet(LogNetConfig(vocab_size=64))(tokens())

    assert tuple(output.encoded.shape) == (4, 40, 128)
    assert tuple(output.template_logits.shape) == (4, 40, 64)
    assert tuple(output.distance.shape) == (4,)


def test_encoder_depth_is_the_specified_six_layers() -> None:
    assert ENCODER_LAYERS == 6
    assert len(LogNet().encoder.layers) == ENCODER_LAYERS


def test_distance_is_a_non_negative_squared_norm() -> None:
    """Sanity for the objective: the score must actually measure distance."""
    model = LogNet(LogNetConfig(vocab_size=8)).eval()
    with torch.no_grad():
        output = model(tokens(batch=1, seq=4, vocab=8))

    assert float(output.distance[0]) >= 0.0


# --- determinism (R-67) ----------------------------------------------------


def test_identical_seeds_produce_identical_outputs() -> None:
    x = tokens()

    torch.manual_seed(7)
    first = LogNet()(x)
    torch.manual_seed(7)
    second = LogNet()(x)

    assert torch.equal(first.template_logits, second.template_logits)
    assert torch.equal(first.distance, second.distance)


def test_different_seeds_produce_different_models() -> None:
    """So the determinism test above cannot pass because seeding is a no-op."""
    x = tokens()

    torch.manual_seed(1)
    first = LogNet()(x)
    torch.manual_seed(2)
    second = LogNet()(x)

    assert not torch.equal(first.distance, second.distance)


def test_eval_mode_is_deterministic_across_calls() -> None:
    model = LogNet().eval()
    x = tokens()

    with torch.no_grad():
        assert torch.equal(model(x).distance, model(x).distance)


# --- both objectives can actually learn ------------------------------------


def test_the_masked_template_head_can_fit_a_batch() -> None:
    """Shape checks pass on a model with a dead head; this one does not."""
    torch.manual_seed(11)
    model = LogNet(LogNetConfig(vocab_size=16, dropout=0.0)).train()
    x = tokens(batch=8, seq=12, vocab=16)
    mask = torch.zeros_like(x, dtype=torch.bool)
    mask[:, ::3] = True
    optimiser = torch.optim.Adam(model.parameters(), lr=1e-2)

    first = float(masked_template_loss(model(x), x, mask))
    for _ in range(120):
        optimiser.zero_grad()
        loss = masked_template_loss(model(x), x, mask)
        loss.backward()
        optimiser.step()
    last = float(masked_template_loss(model(x), x, mask))

    # Measured before asserting: 120 steps take this from about 2.7 to under 0.2.
    assert last < first / 4, f"loss only fell from {first:.4f} to {last:.4f}"


def test_the_hypersphere_objective_pulls_windows_toward_the_centre() -> None:
    torch.manual_seed(13)
    model = LogNet(LogNetConfig(vocab_size=16, dropout=0.0)).train()
    x = tokens(batch=8, seq=12, vocab=16)
    optimiser = torch.optim.Adam(model.parameters(), lr=1e-2)

    first = float(hypersphere_loss(model(x)))
    for _ in range(100):
        optimiser.zero_grad()
        loss = hypersphere_loss(model(x))
        loss.backward()
        optimiser.step()
    last = float(hypersphere_loss(model(x)))

    assert last < first, f"distance from centre rose from {first:.4f} to {last:.4f}"


def test_gradients_reach_every_parameter() -> None:
    """Neither objective may leave part of the model untrained."""
    torch.manual_seed(17)
    model = LogNet(LogNetConfig(vocab_size=16, dropout=0.0)).train()
    x = tokens(batch=4, seq=8, vocab=16)
    mask = torch.zeros_like(x, dtype=torch.bool)
    mask[:, ::2] = True
    (masked_template_loss(model(x), x, mask) + hypersphere_loss(model(x))).backward()

    starved = [name for name, p in model.named_parameters() if p.grad is None or not p.grad.any()]
    assert not starved, f"no gradient reached: {starved}"


# --- validation ------------------------------------------------------------


def test_wrong_shapes_and_out_of_vocab_tokens_are_rejected() -> None:
    model = LogNet(LogNetConfig(vocab_size=16))

    with pytest.raises(ValueError, match=r"expected \(batch, seq\)"):
        model(torch.zeros(4, 8, 2, dtype=torch.long))
    with pytest.raises(ValueError, match="outside vocab"):
        model(torch.full((1, 4), 99, dtype=torch.long))


def test_config_rejects_unusable_shapes() -> None:
    with pytest.raises(ValueError, match="vocab_size"):
        LogNetConfig(vocab_size=1)
    with pytest.raises(ValueError, match="mask_token_id"):
        LogNetConfig(vocab_size=8, mask_token_id=8)
    with pytest.raises(ValueError, match="divisible by nhead"):
        LogNetConfig(d_model=65, nhead=8)
    with pytest.raises(ValueError, match="dropout"):
        LogNetConfig(dropout=1.0)
    with pytest.raises(ValueError, match="mask_ratio"):
        LogNetConfig(mask_ratio=0.0)
    with pytest.raises(ValueError, match="max_seq_len"):
        LogNetConfig(max_seq_len=0)


def test_masked_loss_rejects_an_unusable_mask() -> None:
    model = LogNet(LogNetConfig(vocab_size=16))
    x = tokens(batch=2, seq=6, vocab=16)
    output = model(x)

    with pytest.raises(ValueError, match="boolean tensor"):
        masked_template_loss(output, x, torch.zeros_like(x))
    with pytest.raises(ValueError, match="nothing to predict"):
        masked_template_loss(output, x, torch.zeros_like(x, dtype=torch.bool))


def test_parameter_count_is_positive_and_recorded() -> None:
    assert parameter_count(LogNet()) > 0
    assert parameter_count(LogNet()) == parameter_count(LogNet())


# --- T-204's acceptance clause: mining stability ---------------------------

from aegis_ml.data.log_parsers import TemplateMiner  # noqa: E402

CORPUS = (
    "Connection from 10.0.0.5 port 22 accepted",
    "Connection from 10.0.0.9 port 22 accepted",
    "Connection from 10.0.0.11 port 22 accepted",
    "Failed password for root from 10.0.0.5",
    "Failed password for root from 10.0.0.9",
    "Failed password for admin from 10.0.0.11",
    "session closed for user root",
    "session closed for user admin",
    "kernel panic not syncing attempted to kill init",
    "Received disconnect from 10.0.0.5 port 22",
)


def test_mining_is_stable_across_re_runs_on_the_same_corpus() -> None:
    """T-204's acceptance criterion.

    If mining were not stable, the template vocabulary would shift between runs,
    and two models trained on the same corpus would not be comparable - nor would
    a model and the miner that scores for it in production.
    """
    first = TemplateMiner.fit(CORPUS)
    second = TemplateMiner.fit(CORPUS)

    assert first.templates == second.templates
    assert first.merge_rounds == second.merge_rounds


def test_mining_is_stable_under_a_shuffled_corpus() -> None:
    """Stronger than re-running: the template set must not depend on arrival order.

    A corpus read in a different order is the same corpus, and a miner whose
    output depends on order cannot be reproduced from the data alone.
    """
    shuffled = tuple(reversed(CORPUS))

    assert TemplateMiner.fit(CORPUS).templates == TemplateMiner.fit(shuffled).templates


def test_mining_actually_generalises_over_the_variable_parts() -> None:
    """Guards the stability tests against passing because nothing was mined."""
    miner = TemplateMiner.fit(CORPUS)

    # Ten messages, three of which differ only by IP and port, must collapse.
    assert len(miner.templates) < len(CORPUS)
