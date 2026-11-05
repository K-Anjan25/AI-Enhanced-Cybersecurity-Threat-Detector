"""The PostgreSQL side of account erasure (NFR-05, R-37).

:class:`~app.services.erasure.UserDeletionTarget` deletes through a :class:`UserStore`.
This is the store that reaches the ``users`` table. Deleting a row cascades in the
schema, so the store does not reimplement it:

* ``api_keys.owner_id`` is ``ON DELETE CASCADE``: the subject's keys go with the row.
* ``alerts.assigned_to``, ``alerts.verdict_by`` and ``model_versions_history.promoted_by``
  are ``ON DELETE SET NULL`` (migration 0006): the alerts and verdicts stay, and the
  pointer to the person is cleared.

Two things sit outside the schema and are handled here, because the schema cannot
reach them. API keys are still held in process (``InMemoryApiKeyStore``), so the
cascade is also run against that store, the same way :class:`InMemoryUserStore` does.
And the subject is identified by ``users.email``, which is what erasure receives.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text


class PostgresUserStore:
    """A :class:`~app.services.erasure.UserStore` over the ``users`` table."""

    __slots__ = ("_engine", "_keys")

    def __init__(self, engine: Engine, *, keys: object | None = None) -> None:
        """Bind to an engine; ``keys`` is the in-process key store the cascade reaches."""
        self._engine = engine
        self._keys = keys

    def erase_owner(self, owner: str, *, replacement: str) -> int:
        """Delete the user row whose email is ``owner``; return the rows removed.

        ``replacement`` is ignored, as in the in-memory store: a deleted row has nowhere
        to carry a tombstone, and the erasure ledger records the erasure.
        """
        with self._engine.begin() as connection:
            result = connection.execute(
                text("DELETE FROM users WHERE email = :email"), {"email": owner}
            )
            removed = int(result.rowcount or 0)
        if removed:
            cascade: Any = getattr(self._keys, "erase_owner", None)
            if callable(cascade):
                cascade(owner, replacement="")
        return removed
