r"""Tests for the ONNX fallback path (T-210).

The tests split deliberately. Everything about *choosing* a backend must pass in
an environment with neither torch nor ONNX installed, because that is the
environment the fallback exists for: if picking the PyTorch path required the
ONNX runtime to be importable, then a container built without the extra could not
start, and a service that cannot start has no latency to fall back from.

Only the round-trip tests need both, and they are skipped when either is absent.
"""

from __future__ import annotations

import pytest
from aegis_ml.serving.onnx_export import (
    MAX_ABSOLUTE_DIFFERENCE,
    OPSET_VERSION,
    OnnxScorer,
    TorchScorer,
    export_flow_net,
    load_scorer,
    onnx_available,
)


class _FakeModel:
    """Stands in for a FlowNet so the choice logic can be tested without torch."""

    def __init__(self) -> None:
        self.eval_calls = 0

    def eval(self) -> _FakeModel:
        self.eval_calls += 1
        return self


class TestAvailability:
    """Asking must never import the thing being asked about."""

    def test_returns_a_bool(self) -> None:
        assert isinstance(onnx_available(), bool)

    def test_asking_does_not_import_onnx(self) -> None:
        """A find_spec probe must not leave ONNX in sys.modules."""
        import sys

        before = "onnxruntime" in sys.modules
        onnx_available()
        assert ("onnxruntime" in sys.modules) == before


class TestBackendNames:
    """The backend label is an audit field, so it is part of the contract."""

    def test_names_are_distinct_and_stable(self) -> None:
        assert TorchScorer.backend == "torch"
        assert OnnxScorer.backend == "onnx"
        assert TorchScorer.backend != OnnxScorer.backend


class TestFallbackChoice:
    """Choosing a backend must work with nothing optional installed."""

    def test_torch_is_returned_when_asked_for(self) -> None:
        scorer, backend = load_scorer(_FakeModel(), prefer="torch")

        assert backend == "torch"
        assert scorer.backend == "torch"

    def test_falls_back_to_torch_when_no_path_is_given(self) -> None:
        """Asking for ONNX without an artifact must not raise."""
        scorer, backend = load_scorer(_FakeModel(), onnx_path=None, prefer="onnx")

        assert backend == "torch"
        assert scorer.backend == "torch"

    def test_falls_back_to_torch_when_the_artifact_is_missing(self) -> None:
        """A configured-but-absent artifact is a fallback, not a startup failure."""
        scorer, backend = load_scorer(
            _FakeModel(), onnx_path="/nonexistent/flownet.onnx", prefer="onnx"
        )

        assert backend == "torch"
        assert scorer.backend == "torch"

    def test_returned_backend_agrees_with_the_scorer(self) -> None:
        """The tuple's second element must not lie about the first."""
        model = _FakeModel()
        for preference in ("torch", "onnx"):
            scorer, backend = load_scorer(model, prefer=preference)
            assert scorer.backend == backend

    def test_unknown_preference_is_refused(self) -> None:
        """A typo must fail loudly, not silently pick something."""
        with pytest.raises(ValueError, match="unknown backend preference"):
            load_scorer(_FakeModel(), prefer="tensorflow")

    def test_torch_scorer_puts_the_model_in_eval_mode(self) -> None:
        model = _FakeModel()

        TorchScorer(model)  # type: ignore[arg-type]

        assert model.eval_calls == 1


class TestMissingRuntime:
    """With the extra absent, the ONNX-only entry points must fail clearly."""

    def test_onnx_scorer_refuses_without_the_runtime(self) -> None:
        if onnx_available():
            pytest.skip("onnxruntime is installed, so construction would be attempted")

        with pytest.raises(RuntimeError, match="onnx and onnxruntime are required"):
            OnnxScorer("/nonexistent/flownet.onnx")

    def test_export_refuses_without_the_runtime(self, tmp_path: object) -> None:
        if onnx_available():
            pytest.skip("onnx is installed, so export would be attempted")

        from pathlib import Path

        target = Path(str(tmp_path)) / "never.onnx"
        with pytest.raises(RuntimeError, match="onnx is required to export"):
            export_flow_net(_FakeModel(), target, window_size=5, input_dim=2)  # type: ignore[arg-type]


class TestConstants:
    """The two numbers the acceptance criteria hang on."""

    def test_opset_is_at_least_18(self) -> None:
        """Torch 2.14 cannot emit below 18 and fails the downgrade conversion."""
        assert OPSET_VERSION >= 18

    def test_tolerance_is_the_acceptance_value(self) -> None:
        assert MAX_ABSOLUTE_DIFFERENCE == 1e-4


# --- round trip: needs both torch and onnx ---------------------------------


def _needs_full_stack() -> None:
    torch = pytest.importorskip("torch")
    if not onnx_available():
        pytest.skip("onnx / onnxruntime not installed")
    return torch


class TestRoundTrip:
    """The exported graph must be the same model, on a fixed batch."""

    def test_agreement_within_tolerance(self) -> None:
        torch = _needs_full_stack()
        import tempfile
        from pathlib import Path

        from aegis_ml.models.flownet import FlowNet, FlowNetConfig

        torch.manual_seed(20260114)
        model = FlowNet(FlowNetConfig(input_dim=6))
        model.eval()
        generator = torch.Generator().manual_seed(20260114)
        batch = torch.rand((8, 50, 6), dtype=torch.float32, generator=generator)

        with tempfile.TemporaryDirectory() as directory:
            artifact = export_flow_net(
                model, Path(directory) / "flownet.onnx", window_size=50, input_dim=6
            )
            reference = TorchScorer(model).score(batch)
            candidate = OnnxScorer(artifact).score(batch)

        for name in ("reconstruction", "anomaly_logits"):
            difference = float((getattr(reference, name) - getattr(candidate, name)).abs().max())
            assert difference <= MAX_ABSOLUTE_DIFFERENCE, f"{name} drifted {difference:.3e}"

    def test_graph_accepts_a_different_batch_size(self) -> None:
        """The axis must stay dynamic; a graph pinned to one batch is not serving."""
        torch = _needs_full_stack()
        import tempfile
        from pathlib import Path

        from aegis_ml.models.flownet import FlowNet, FlowNetConfig

        torch.manual_seed(7)
        model = FlowNet(FlowNetConfig(input_dim=6))
        model.eval()

        with tempfile.TemporaryDirectory() as directory:
            artifact = export_flow_net(
                model, Path(directory) / "flownet.onnx", window_size=50, input_dim=6
            )
            scorer = OnnxScorer(artifact)
            shapes = []
            for size in (1, 4, 16):
                batch = torch.rand((size, 50, 6), dtype=torch.float32)
                shapes.append(tuple(scorer.score(batch).anomaly_logits.shape))

        assert shapes == [(1,), (4,), (16,)]

    def test_load_scorer_prefers_the_artifact_when_present(self) -> None:
        torch = _needs_full_stack()
        import tempfile
        from pathlib import Path

        from aegis_ml.models.flownet import FlowNet, FlowNetConfig

        torch.manual_seed(3)
        model = FlowNet(FlowNetConfig(input_dim=6))
        model.eval()

        with tempfile.TemporaryDirectory() as directory:
            artifact = export_flow_net(
                model, Path(directory) / "flownet.onnx", window_size=50, input_dim=6
            )
            scorer, backend = load_scorer(model, onnx_path=artifact, prefer="onnx")

        assert backend == "onnx"
        assert scorer.backend == "onnx"
