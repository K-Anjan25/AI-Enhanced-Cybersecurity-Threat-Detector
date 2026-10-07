"""Wire contracts for webhook configuration and delivery (FR-21, T-311, T-422).

The split between :class:`WebhookOut` and :class:`WebhookCreatedOut` is the
security property rather than a formatting choice: the signing secret is a field
of the creation response and of nothing else, so a listing cannot leak it by
being written carelessly. There is deliberately no schema anywhere in this module
that carries a secret alongside a stored target.

:class:`DeliveryOut` is the read half T-311 did not have: what an attempt to
reach one of these targets did. It carries the target by *id* and the outcome by
code, so a delivery list is safe to show beside the configuration without
repeating either the URL or the credential.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "DeliveryListOut",
    "DeliveryOut",
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


class DeliveryOut(BaseModel):
    """One delivery attempt, as the connectors screen reads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    delivery_id: str
    target_id: str
    at: datetime = Field(description="When the delivery finished, on the API's clock.")
    delivered: bool
    attempt_count: int = Field(description="Requests made, retries included.")
    waited_seconds: float = Field(description="Time spent in backoffs between them.")
    outcome: str = Field(
        description="The last attempt: delivered, retry, rejected, blocked or transport_error."
    )
    status: int | None = Field(default=None, description="HTTP status of the last attempt.")
    reason: str = Field(description="A short code, never a message from the receiver.")


class DeliveryListOut(BaseModel):
    """Recent delivery attempts, newest first, with what qualifies them (R-70)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[DeliveryOut]
    held: int = Field(description="How many records the process still holds.")
    recorded: int = Field(description="How many it has made, including dropped ones.")
    dispatch_configured: bool = Field(
        description="Whether this deployment has a sender, so an empty list can be read."
    )
    caveats: list[str]
