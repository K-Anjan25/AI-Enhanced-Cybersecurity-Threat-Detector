"""Wire contracts for webhook configuration (FR-21, T-311).

The split between :class:`WebhookOut` and :class:`WebhookCreatedOut` is the
security property rather than a formatting choice: the signing secret is a field
of the creation response and of nothing else, so a listing cannot leak it by
being written carelessly. There is deliberately no schema anywhere in this module
that carries a secret alongside a stored target.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "WebhookCreate",
    "WebhookCreatedOut",
    "WebhookListOut",
    "WebhookOut",
]

#: An operator note, not a document store.
MAX_DESCRIPTION_LENGTH = 200

#: FR-21's severity floor: high and critical are delivered by default. Expressed
#: as a floor so a deployment can raise it without a code change.
DEFAULT_SEVERITY_FLOOR = "high"


class WebhookCreate(BaseModel):
    """A webhook target to register."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str = Field(min_length=1, max_length=2048, description="https:// destination.")
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    severity_floor: str = Field(
        default=DEFAULT_SEVERITY_FLOOR,
        description="Lowest severity delivered: info, low, medium, high or critical.",
    )


class WebhookOut(BaseModel):
    """A configured target, **without** its secret."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    url: str
    description: str | None
    severity_floor: str
    active: bool
    created_at: datetime


class WebhookCreatedOut(BaseModel):
    """A newly registered target, with its secret shown exactly once.

    The secret cannot be retrieved again: it is stored sealed, and the API has
    no route that opens it. An operator who loses it re-issues the target.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    url: str
    description: str | None
    severity_floor: str
    active: bool
    created_at: datetime
    secret: str = Field(description="Signing secret. Shown once; store it now.")


class WebhookListOut(BaseModel):
    """Every configured target."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[WebhookOut]
