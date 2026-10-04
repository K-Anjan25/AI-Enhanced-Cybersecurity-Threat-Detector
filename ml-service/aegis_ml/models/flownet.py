"""``FlowNet``: a transformer over flow windows (T-201).

The architecture is the one ``architecture.md`` §6 specifies — a projection into
an embedding space, a four-layer transformer encoder, and two heads — and the
two heads are not redundant:

* the **reconstruction** head is trained to reproduce its own input. It is what
  makes the model an anomaly detector rather than a classifier: traffic that
  resembles the training distribution reconstructs cleanly, traffic that does
  not leaves a residue. That residue is available on unlabelled data, which is
  the whole reason to prefer this over a supervised-only model.
* the **anomaly** head is a supervised read-out, trained where labels exist.

Both are returned from one forward pass so that a caller can compare them, and
so that a disagreement between the two is observable rather than hidden. At
inference the composite score is T-205's job, not this module's.

Everything here is deterministic given a seed. ``torch.manual_seed`` is not
called implicitly — the caller seeds, because a model that seeds itself cannot
be embedded in a larger reproducible pipeline (R-67).

torch is an optional extra (``ml-service[training]``) rather than a hard
dependency: the service must install, typecheck and serve without a 3 GB
deep-learning stack present.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, cast

import torch
from torch import Tensor, nn

from aegis_ml.data.features import FEATURE_NAMES
from aegis_ml.data.windowing import FLOW_WINDOW_SIZE

#: Number of encoder layers. Fixed by architecture.md §6, not a tuning knob:
#: changing it changes the model identity, so it belongs in the constant rather
#: than in a config a caller can quietly edit.
ENCODER_LAYERS: Final = 4


@dataclass(frozen=True, slots=True)
class FlowNetConfig:
    """Hyperparameters for :class:`FlowNet`.

    Attributes:
        input_dim: width of one timestep. Defaults to the ``features@1`` vector.
        d_model: embedding width the encoder works in.
        nhead: attention heads. Must divide ``d_model``.
        dim_feedforward: width of the position-wise feed-forward layer.
        dropout: applied to embeddings, attention and the feed-forward layer.
        max_seq_len: longest window the positional encoding supports.
    """

    input_dim: int = len(FEATURE_NAMES)
    # Sized against T-201's second acceptance clause - parameter count within 20%
    # of a 1.2 M target - not chosen by taste. Measured, not estimated: 176/448
    # gives 1,158,840 at input_dim 23 and 1,163,076 at 35, so the default stays
    # inside the band whichever one-hot width a dataset produces. d_model 128
    # (807,704) misses low and 192/384 lands closer to the ceiling.
    d_model: int = 176
    nhead: int = 8
    dim_feedforward: int = 448
    dropout: float = 0.1
    max_seq_len: int = FLOW_WINDOW_SIZE

    def __post_init__(self) -> None:
        """Reject shapes that would fail deep inside torch with an opaque error."""
        if self.input_dim < 1:
            raise ValueError(f"input_dim must be positive, got {self.input_dim}")
        if self.d_model % self.nhead != 0:
            raise ValueError(f"d_model ({self.d_model}) must be divisible by nhead ({self.nhead})")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError(f"dropout must be in [0, 1), got {self.dropout}")
        if self.max_seq_len < 1:
            raise ValueError(f"max_seq_len must be positive, got {self.max_seq_len}")


@dataclass(frozen=True, slots=True)
class FlowNetOutput:
    """One forward pass.

    Attributes:
        reconstruction: ``(batch, seq, input_dim)`` — the model's attempt to
            reproduce the input.
        anomaly_logits: ``(batch,)`` — unnormalised anomaly score per window.
            Logits, not probabilities: thresholding and calibration are T-207's
            job, and taking a sigmoid here would discard information the caller
            may need.
    """

    reconstruction: Tensor
    anomaly_logits: Tensor


class _PositionalEncoding(nn.Module):
    """Fixed sinusoidal positions.

    Learned positions would work too, but a fixed encoding adds no parameters,
    generalises to sequences shorter than anything seen in training, and cannot
    drift between runs — which matters more here than a fraction of a metric.
    """

    def __init__(self, d_model: int, max_seq_len: int, dropout: float) -> None:
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        encoding = torch.zeros(max_seq_len, d_model)
        position = torch.arange(0, max_seq_len, dtype=torch.float32).unsqueeze(1)
        divisor = torch.exp(
            torch.arange(0, d_model, 2, dtype=torch.float32) * (-math.log(10000.0) / d_model)
        )
        encoding[:, 0::2] = torch.sin(position * divisor)
        encoding[:, 1::2] = torch.cos(position * divisor[: encoding[:, 1::2].shape[1]])
        # (1, max_seq_len, d_model) so it broadcasts over the batch dimension.
        self.encoding: Tensor  # assigned by register_buffer below
        self.register_buffer("encoding", encoding.unsqueeze(0), persistent=False)

    def forward(self, x: Tensor) -> Tensor:
        """Add positions to ``x`` and apply dropout."""
        if x.size(1) > self.encoding.size(1):
            raise ValueError(
                f"sequence of length {x.size(1)} exceeds max_seq_len " f"{self.encoding.size(1)}"
            )
        return cast(Tensor, self.dropout(x + self.encoding[:, : x.size(1)]))


class FlowNet(nn.Module):
    """A four-layer transformer over a window of flow vectors.

    Input shape is ``(batch, seq, input_dim)``: one window is a sequence of flow
    records, and the transformer's job is to model the *order* — beaconing and
    slow exfiltration are visible in the spacing of a window and invisible in
    any aggregate of it.
    """

    def __init__(self, config: FlowNetConfig | None = None) -> None:
        """Build the projection, encoder and both heads from ``config``."""
        super().__init__()
        self.config = config or FlowNetConfig()
        c = self.config

        self.projection = nn.Linear(c.input_dim, c.d_model)
        self.positions = _PositionalEncoding(c.d_model, c.max_seq_len, c.dropout)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=c.d_model,
            nhead=c.nhead,
            dim_feedforward=c.dim_feedforward,
            dropout=c.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        # enable_nested_tensor is off because norm_first makes it inert; leaving
        # it on emits a warning on every construction, which trains people to
        # read past warnings.
        self.encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=ENCODER_LAYERS, enable_nested_tensor=False
        )
        self.norm = nn.LayerNorm(c.d_model)

        self.reconstruction_head = nn.Linear(c.d_model, c.input_dim)
        self.anomaly_head = nn.Sequential(
            nn.Linear(c.d_model, c.d_model // 2),
            nn.GELU(),
            nn.Linear(c.d_model // 2, 1),
        )

    def encode(self, x: Tensor) -> Tensor:
        """Run the projection, positional encoding and encoder.

        Exposed separately from :meth:`forward` because T-205's late fusion and
        T-206's attention explanations both need the encoded representation
        rather than the head outputs.
        """
        if x.dim() != 3:
            raise ValueError(
                f"expected (batch, seq, {self.config.input_dim}), got {tuple(x.shape)}"
            )
        if x.size(2) != self.config.input_dim:
            raise ValueError(
                f"expected {self.config.input_dim} features per timestep, got {x.size(2)}"
            )
        embedded = self.positions(self.projection(x))
        return cast(Tensor, self.norm(self.encoder(embedded)))

    def forward(self, x: Tensor) -> FlowNetOutput:
        """Encode ``x`` and run both heads."""
        encoded = self.encode(x)
        return FlowNetOutput(
            reconstruction=cast(Tensor, self.reconstruction_head(encoded)),
            # Mean-pool over the sequence: an anomaly is a property of the whole
            # window, and pooling keeps the head independent of window length.
            anomaly_logits=cast(Tensor, self.anomaly_head(encoded.mean(dim=1)).squeeze(-1)),
        )


def parameter_count(model: nn.Module) -> int:
    """Total trainable parameters. Part of T-201's acceptance criteria."""
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)


def reconstruction_error(output: FlowNetOutput, target: Tensor) -> Tensor:
    """Mean squared error between the reconstruction and its input.

    Kept out of the model so the loss stays swappable — T-204 uses a different
    reconstruction target, and a model that hard-codes its own loss cannot be
    reused for it.
    """
    return nn.functional.mse_loss(output.reconstruction, target)
