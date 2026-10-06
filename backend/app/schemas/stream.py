"""Wire contracts for the alert stream (FR-20, T-310).

A pushed alert is deliberately the *same* row model the query API returns
(:class:`~app.schemas.query.AlertRow`), wrapped with the position it occupies in
the stream. A dashboard then renders a pushed alert and a fetched alert with one
code path, and the two shapes cannot drift.

``epoch`` is part of every catch-up response, not only the socket handshake:
sequences are per-process, so a client whose cursor came from a previous process
must be told that its cursor is meaningless rather than being handed a
confidently wrong "you are up to date".
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.query import AlertRow

__all__ = [
    "AlertNotificationOut",
    "AlertNotificationsOut",
]


class AlertNotificationOut(BaseModel):
    """One alert plus its stream position."""

    model_config = ConfigDict(frozen=True)

    sequence: int
    alert: AlertRow


class AlertNotificationsOut(BaseModel):
    """The polling fallback, and what a client gets when it must resync.

    Attributes:
        items: notifications after the requested cursor, oldest first.
        oldest_available: the oldest sequence the hub still retains.
        latest: the newest sequence published, or ``None`` when nothing has been.
        resync_required: True when the cursor predates the retained window, so
            ``items`` is not the whole gap and the client must re-query alerts
            instead of assuming it is current.
        epoch: the publishing process's stream identity.
    """

    model_config = ConfigDict(frozen=True)

    items: list[AlertNotificationOut]
    oldest_available: int | None
    latest: int | None
    resync_required: bool
    epoch: str
