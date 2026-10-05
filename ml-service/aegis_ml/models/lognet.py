"""``LogNet``: a from-scratch transformer over mined log templates (T-204).

Q-01 decided this is not a pretrained language model (D-019). T-104 measured 103
templates over 2,000 BGL lines at 0.9530 purity, so a log window is a sequence
drawn from roughly a hundred discrete tokens — there is little language left for
English pretraining to transfer, and NFR-05's 150 ms cap rules out DistilBERT over
a 200-line window on CPU anyway.

Both losses are self-supervised, because unlabelled logs are the production case:

* **masked-template** prediction replaces some tokens with a mask and asks the
  encoder to recover them. It teaches what normally follows what, which is the
  structure an anomalous sequence violates.
* the **hypersphere** objective pulls representations of ordinary windows toward
  a learned centre. Anomaly is then distance from that centre — no threshold on a
  supervised score, and nothing that requires labels to compute.

What this design cannot see is recorded in D-019 rather than left implicit: novel
*wording* is invisible, because an unseen message collapses to an unknown-template
token. That is why ``template_known`` is a feature at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, cast

import torch
from torch import Tensor, nn

from aegis_ml.data.windowing import LOG_WINDOW_SIZE

from .flownet import _PositionalEncoding

#: Number of encoder layers. Six, per architecture.md §6 — deeper than FlowNet's
#: four, because a log window is four times longer and the structure that matters
#: (a sequence of events) is spread across it.
ENCODER_LAYERS: Final = 6


@dataclass(frozen=True, slots=True)
class LogNetConfig:
    """Hyperparameters for :class:`LogNet`.

    Attributes:
        vocab_size: number of mined templates, plus reserved ids.
        mask_token_id: the reserved id substituted for masked positions.
        d_model: embedding width.
        nhead: attention heads; must divide ``d_model``.
        dim_feedforward: width of the position-wise feed-forward layer.
        dropout: applied to embeddings, attention and the feed-forward layer.
        max_seq_len: longest window the positional encoding supports.
        mask_ratio: share of positions masked during training.
    """

    vocab_size: int = 128
    mask_token_id: int = 0
    d_model: int = 128
    nhead: int = 8
    dim_feedforward: int = 256
    dropout: float = 0.1
    max_seq_len: int = LOG_WINDOW_SIZE
    mask_ratio: float = 0.15

    def __post_init__(self) -> None:
        """Reject shapes that would otherwise fail opaquely inside torch."""
        if self.vocab_size < 2:
            raise ValueError(f"vocab_size must be at least 2, got {self.vocab_size}")
        if not 0 <= self.mask_token_id < self.vocab_size:
            raise ValueError(
                f"mask_token_id {self.mask_token_id} outside vocab of {self.vocab_size}"
            )
        if self.d_model % self.nhead != 0:
            raise ValueError(f"d_model ({self.d_model}) must be divisible by nhead ({self.nhead})")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError(f"dropout must be in [0, 1), got {self.dropout}")
        if not 0.0 < self.mask_ratio < 1.0:
            raise ValueError(f"mask_ratio must be in (0, 1), got {self.mask_ratio}")
        if self.max_seq_len < 1:
            raise ValueError(f"max_seq_len must be positive, got {self.max_seq_len}")


@dataclass(frozen=True, slots=True)
class LogNetOutput:
    """One forward pass.

    Attributes:
        encoded: ``(batch, seq, d_model)`` per-position representations.
        template_logits: ``(batch, seq, vocab_size)`` — the masked-template head.
        distance: ``(batch,)`` — squared distance of the pooled window from the
            hypersphere centre. This is the anomaly score.
    """

    encoded: Tensor
    template_logits: Tensor
    distance: Tensor


class LogNet(nn.Module):
    """A six-layer transformer over a window of template ids."""

    def __init__(self, config: LogNetConfig | None = None) -> None:
        """Build the embedding, encoder and both objectives from ``config``."""
        super().__init__()
        self.config = config or LogNetConfig()
        c = self.config

        self.embedding = nn.Embedding(c.vocab_size, c.d_model, padding_idx=None)
        self.positions = _PositionalEncoding(c.d_model, c.max_seq_len, c.dropout)
        layer = nn.TransformerEncoderLayer(
            d_model=c.d_model,
            nhead=c.nhead,
            dim_feedforward=c.dim_feedforward,
            dropout=c.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            layer, num_layers=ENCODER_LAYERS, enable_nested_tensor=False
        )
        self.norm = nn.LayerNorm(c.d_model)

        self.template_head = nn.Linear(c.d_model, c.vocab_size)
        # Initialised on the unit sphere and trained with the representations, so
        # "distance from centre" is meaningful from the first step rather than
        # after the centre happens to drift somewhere sensible.
        centre = torch.zeros(c.d_model)
        centre[0] = 1.0
        self.centre = nn.Parameter(centre)

    def encode(self, token_ids: Tensor) -> Tensor:
        """Embed, add positions and run the encoder.

        Exposed separately from :meth:`forward` because T-205's fusion needs the
        representation and T-206's explanation needs the attention, not the heads.
        """
        if token_ids.dim() != 2:
            raise ValueError(f"expected (batch, seq) token ids, got {tuple(token_ids.shape)}")
        if int(token_ids.max()) >= self.config.vocab_size:
            raise ValueError(
                f"token id {int(token_ids.max())} outside vocab of {self.config.vocab_size}"
            )
        embedded = self.positions(self.embedding(token_ids))
        return cast(Tensor, self.norm(self.encoder(embedded)))

    def forward(self, token_ids: Tensor) -> LogNetOutput:
        """Encode ``token_ids`` and run both heads."""
        encoded = self.encode(token_ids)
        pooled = encoded.mean(dim=1)
        return LogNetOutput(
            encoded=encoded,
            template_logits=cast(Tensor, self.template_head(encoded)),
            # Squared distance, not its root: the ordering is the same, and
            # skipping the sqrt keeps the gradient well behaved near the centre.
            distance=((pooled - self.centre) ** 2).sum(dim=-1),
        )


def masked_template_loss(output: LogNetOutput, targets: Tensor, mask: Tensor) -> Tensor:
    """Cross-entropy over masked positions only.

    Scoring unmasked positions too would let the model win by copying its input,
    which teaches nothing about what normally follows what.
    """
    if mask.dtype != torch.bool:
        raise ValueError("mask must be a boolean tensor")
    if not bool(mask.any()):
        raise ValueError("no positions are masked, so there is nothing to predict")
    logits = output.template_logits[mask]
    return nn.functional.cross_entropy(logits, targets[mask])


def hypersphere_loss(output: LogNetOutput) -> Tensor:
    """Pull every window in the batch toward the centre.

    There is no repulsive term, so this objective is only meaningful on ordinary
    traffic: trained on a batch containing attacks, it teaches the model that
    attacks are normal. Callers must pass benign windows.
    """
    return output.distance.mean()


def parameter_count(model: nn.Module) -> int:
    """Total trainable parameters."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
