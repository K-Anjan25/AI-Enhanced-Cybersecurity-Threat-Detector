r"""ONNX export and the runtime fallback (T-210).

ONNX is the documented latency fallback (prd.md risk register, architecture.md
CPU-first inference), not the primary path. That shapes everything here:

* **Nothing in this module may require ONNX to be installed.** The fallback exists
  for the moment PyTorch inference is too slow, but if importing this file needed
  the ONNX runtime then the service could not start without it — and a service
  that cannot start has no latency to fall back from. Both imports are lazy and
  :func:`onnx_available` is the only way to ask.
* **Choosing a backend is a decision the caller can see.** :func:`load_scorer`
  returns the backend it picked alongside the scorer, because "which model scored
  this alert" is an audit question and a silent fallback would answer it wrongly.
* **A fallback must not be a second implementation.** The ONNX graph is exported
  from the same ``FlowNet`` weights, and `scripts/onnx_export.py` fails the build
  if the two disagree by more than 1e-4. A fallback whose numbers drift from the
  primary path is a second model wearing the first one's name.

Note the measurement that motivates keeping this optional rather than default:
T-209 recorded p95 22.590 ms per window against a 150 ms budget, so the PyTorch
path is already ~6.6x inside budget and this path is preparedness, not a fix.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from torch import Tensor

    from aegis_ml.models.flownet import FlowNet

#: The opset this module exports at.
#:
#: Not a stylistic choice. torch 2.14 refuses to emit 17 and then fails the
#: automatic downgrade conversion, so 18 is the floor that actually produces a
#: loadable graph.
OPSET_VERSION = 18

#: T-210's acceptance tolerance. Wider than this and the export is not the model.
MAX_ABSOLUTE_DIFFERENCE = 1e-4


def onnx_available() -> bool:
    """Whether both the exporter and the runtime can be imported.

    Uses :mod:`importlib.util` rather than a ``try/except ImportError`` around a
    real import: this is called from module import paths, and an import that
    partially executes before failing can leave a broken module in ``sys.modules``
    for the next caller to trip over.
    """
    return (
        importlib.util.find_spec("onnx") is not None
        and importlib.util.find_spec("onnxruntime") is not None
    )


@dataclass(frozen=True, slots=True)
class ScoredWindow:
    """Both heads for one scored batch.

    Attributes:
        reconstruction: ``(batch, seq, input_dim)``.
        anomaly_logits: ``(batch,)`` — logits, matching
            :class:`~aegis_ml.models.flownet.FlowNetOutput`.
        backend: which scorer produced this, so a caller can record it.
    """

    reconstruction: Tensor
    anomaly_logits: Tensor
    backend: str


class Scorer(Protocol):
    """The common surface the two backends share."""

    backend: str

    def score(self, window: Tensor) -> ScoredWindow:
        """Score one batch of windows."""
        ...


class TorchScorer:
    """Scores through PyTorch. The primary path."""

    backend = "torch"

    def __init__(self, model: FlowNet) -> None:
        """Wrap a trained model and put it in eval mode."""
        self._model = model
        self._model.eval()

    def score(self, window: Tensor) -> ScoredWindow:
        """One forward pass under ``no_grad``."""
        import torch  # noqa: PLC0415

        with torch.no_grad():
            output = self._model(window)
        return ScoredWindow(
            reconstruction=output.reconstruction,
            anomaly_logits=output.anomaly_logits,
            backend=self.backend,
        )


class OnnxScorer:
    """Scores through the exported ONNX graph.

    Raises :class:`RuntimeError` at construction if the runtime is missing, rather
    than at first score: a scorer that only fails when an alert arrives has failed
    at the worst possible moment.
    """

    backend = "onnx"

    def __init__(self, path: str | Path) -> None:
        """Open an exported graph, or fail here rather than at scoring time."""
        if not onnx_available():
            raise RuntimeError(
                "onnx and onnxruntime are required to score through an exported "
                "graph; install ml-service[onnx]"
            )
        import onnxruntime  # noqa: PLC0415

        self._path = Path(path)
        if not self._path.is_file():
            raise FileNotFoundError(f"no ONNX artifact at {self._path}")
        # A single intra-op thread: T-209 measured two threads as slower than one
        # on a window this small, so the ONNX path should not reintroduce the
        # coordination overhead the PyTorch path was tuned away from.
        self._session = onnxruntime.InferenceSession(
            str(self._path),
            providers=["CPUExecutionProvider"],
            sess_options=_single_thread_options(),
        )
        self._input_name = self._session.get_inputs()[0].name

    def score(self, window: Tensor) -> ScoredWindow:
        """Run the graph and wrap the outputs back into tensors."""
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415

        values = window.detach().cpu().numpy()
        reconstruction, anomaly_logits = self._session.run(None, {self._input_name: values})
        return ScoredWindow(
            reconstruction=torch.from_numpy(np.asarray(reconstruction)),
            anomaly_logits=torch.from_numpy(np.asarray(anomaly_logits)),
            backend=self.backend,
        )


def _single_thread_options() -> object:
    """Onnxruntime session options pinned to one intra-op thread."""
    import onnxruntime  # noqa: PLC0415

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    return options


def export_flow_net(
    model: FlowNet,
    path: str | Path,
    *,
    window_size: int,
    input_dim: int,
    opset: int = OPSET_VERSION,
) -> Path:
    """Export ``model`` to ONNX and return the written path.

    Batch and sequence length are dynamic axes: a service scores one window at a
    time and batches opportunistically, so a graph pinned to one shape would need
    re-exporting for every caller.

    ``dynamo=False`` is required, and was found by measurement rather than by
    preference. torch 2.14's default exporter goes through ``torch.export``, which
    specialises the batch dimension: the graph loads and scores a batch of one,
    then fails at any other batch size on a Reshape node that has the batch count
    baked in as a constant. The TorchScript-based exporter keeps the axis dynamic.
    A graph that only works at one batch size is not a serving path.

    Raises:
        RuntimeError: if the exporter is not installed.
    """
    if not onnx_available():
        raise RuntimeError("onnx is required to export a FlowNet graph; install ml-service[onnx]")

    import torch  # noqa: PLC0415

    class _Exportable(torch.nn.Module):
        """FlowNet returns a dataclass; ONNX wants a tuple of tensors."""

        def __init__(self, inner: FlowNet) -> None:
            super().__init__()
            self.inner = inner

        def forward(self, window: Tensor) -> tuple[Tensor, Tensor]:
            output = self.inner(window)
            return output.reconstruction, output.anomaly_logits

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    wrapper = _Exportable(model)
    wrapper.eval()
    example = torch.zeros((1, window_size, input_dim), dtype=torch.float32)
    torch.onnx.export(
        wrapper,
        (example,),
        str(target),
        input_names=["window"],
        output_names=["reconstruction", "anomaly_logits"],
        dynamic_axes={
            "window": {0: "batch", 1: "steps"},
            "reconstruction": {0: "batch", 1: "steps"},
            "anomaly_logits": {0: "batch"},
        },
        opset_version=opset,
        dynamo=False,
    )
    return target


def load_scorer(
    torch_model: FlowNet,
    *,
    onnx_path: str | Path | None = None,
    prefer: str = "onnx",
) -> tuple[Scorer, str]:
    """Return ``(scorer, backend)``, falling back to PyTorch when it must.

    ``prefer="onnx"`` asks for the exported graph but never requires it: if the
    runtime is missing, no path was given, or the artifact is not on disk, the
    PyTorch scorer is returned instead. The chosen backend comes back in the tuple
    so the caller can log it — a silent fallback that scored an alert from a
    different backend than the one recorded is worse than no fallback at all.

    Raises:
        ValueError: if ``prefer`` is not a known backend.
    """
    if prefer not in ("onnx", "torch"):
        raise ValueError(f"unknown backend preference {prefer!r}")
    if prefer == "torch":
        return TorchScorer(torch_model), TorchScorer.backend
    if not onnx_available() or onnx_path is None:
        return TorchScorer(torch_model), TorchScorer.backend
    try:
        scorer = OnnxScorer(onnx_path)
    except (RuntimeError, FileNotFoundError):
        return TorchScorer(torch_model), TorchScorer.backend
    return scorer, scorer.backend
