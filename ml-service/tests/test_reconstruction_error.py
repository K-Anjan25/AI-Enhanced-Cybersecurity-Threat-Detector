"""Tests for per-window reconstruction error, the signal T-208 transfers on.

The interesting property is not that the function computes a mean square error.
It is that it must agree with :func:`reconstruction_error` — the training loss —
while returning one number per window instead of one per batch. If the two ever
diverge, the model trains on one notion of anomalous and the detector reports
another, and nothing in the pipeline would notice.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from aegis_ml.models.flownet import (  # noqa: E402
    FlowNet,
    FlowNetConfig,
    FlowNetOutput,
    per_window_reconstruction_error,
    reconstruction_error,
)


def _output(reconstruction: list[list[list[float]]]) -> FlowNetOutput:
    """Build a FlowNetOutput carrying a chosen reconstruction.

    Only ``reconstruction`` is set from the argument; ``anomaly_logits`` is
    irrelevant to this function and is filled with a matching batch size.
    """
    reconstruction_tensor = torch.tensor(reconstruction, dtype=torch.float32)
    return FlowNetOutput(
        reconstruction=reconstruction_tensor,
        anomaly_logits=torch.zeros((reconstruction_tensor.shape[0],), dtype=torch.float32),
    )


class TestShape:
    """It must return one number per window, not one per batch."""

    def test_one_score_per_window(self) -> None:
        output = _output([[[1.0, 2.0]], [[3.0, 4.0]], [[5.0, 6.0]]])
        target = torch.zeros((3, 1, 2), dtype=torch.float32)

        error = per_window_reconstruction_error(output, target)

        assert tuple(error.shape) == (3,)

    def test_averages_over_timesteps_and_features(self) -> None:
        """A window of two timesteps collapses to its mean, not its sum."""
        output = _output([[[1.0, 1.0], [3.0, 3.0]]])
        target = torch.zeros((1, 2, 2), dtype=torch.float32)

        error = per_window_reconstruction_error(output, target)

        # (1 + 1 + 9 + 9) / 4 = 5.0, not 20.0.
        assert float(error[0]) == pytest.approx(5.0)

    def test_perfect_reconstruction_scores_zero(self) -> None:
        target = torch.tensor([[[1.0, 2.0], [3.0, 4.0]]], dtype=torch.float32)
        output = _output([[[1.0, 2.0], [3.0, 4.0]]])

        error = per_window_reconstruction_error(output, target)

        assert float(error[0]) == pytest.approx(0.0)


class TestAgreementWithTheLoss:
    """The detector must measure the same thing the trainer optimised."""

    def test_mean_of_per_window_equals_the_scalar_loss(self) -> None:
        target = torch.tensor(
            [[[1.0, 2.0], [3.0, 0.5]], [[0.0, 0.0], [4.0, 4.0]], [[1.5, 2.5], [0.25, 0.75]]],
            dtype=torch.float32,
        )
        output = _output(
            [
                [[1.5, 2.0], [3.0, 0.0]],
                [[0.25, 0.25], [4.0, 3.0]],
                [[1.5, 2.0], [0.25, 0.75]],
            ]
        )

        per_window = per_window_reconstruction_error(output, target)
        scalar = reconstruction_error(output, target)

        assert float(per_window.mean()) == pytest.approx(float(scalar), rel=1e-6)

    def test_agreement_holds_for_a_real_forward_pass(self) -> None:
        """Not just for hand-built outputs — through the actual model too."""
        model = FlowNet(FlowNetConfig(input_dim=6))
        model.eval()
        target = torch.rand((4, 5, 6), dtype=torch.float32)
        with torch.no_grad():
            output = model(target)
            per_window = per_window_reconstruction_error(output, target)
            scalar = reconstruction_error(output, target)

        assert tuple(per_window.shape) == (4,)
        assert float(per_window.mean()) == pytest.approx(float(scalar), rel=1e-6)


class TestOrdering:
    """A worse-reconstructed window must score higher, or detection is noise."""

    def test_worse_reconstruction_scores_higher(self) -> None:
        target = torch.zeros((3, 1, 1), dtype=torch.float32)
        output = _output([[[0.1]], [[1.0]], [[3.0]]])

        error = per_window_reconstruction_error(output, target)

        assert float(error[0]) < float(error[1]) < float(error[2])

    def test_ranks_the_perturbed_window_first(self) -> None:
        """The realistic case: one window in a batch departs from benign."""
        benign = [[1.0, 1.0], [1.0, 1.0]]
        target = torch.tensor([benign, benign, [[1.0, 1.0], [9.0, 9.0]]], dtype=torch.float32)
        output = _output([[[1.0, 1.0], [1.0, 1.0]], benign, [[1.0, 1.0], [0.5, 0.5]]])

        error = per_window_reconstruction_error(output, target)

        assert int(error.argmax()) == 2


class TestValidation:
    """A silent shape mismatch would compare the wrong timesteps."""

    def test_rejects_mismatched_shapes(self) -> None:
        output = _output([[[1.0, 2.0]]])
        target = torch.zeros((1, 3, 2), dtype=torch.float32)

        with pytest.raises(ValueError, match="does not match"):
            per_window_reconstruction_error(output, target)

    def test_rejects_mismatched_feature_width(self) -> None:
        output = _output([[[1.0, 2.0]]])
        target = torch.zeros((1, 1, 5), dtype=torch.float32)

        with pytest.raises(ValueError, match="does not match"):
            per_window_reconstruction_error(output, target)
