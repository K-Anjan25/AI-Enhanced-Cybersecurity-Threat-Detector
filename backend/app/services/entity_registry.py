"""The ids alerts reference, and the names those ids stand for (T-319, T-416).

``alerts.entity_id`` is a foreign key into ``entities``, and the persistent source
of that id is the table's Identity column. The ingest path does not write
``entities`` yet, so :class:`EntityRegistry` allocates in memory: stable per
``(kind, value)``, assigned on first sight, so two detections about one host are
one entity. The id is meaningful within a process and nowhere else, which is a
recorded gap and not presented as the real thing.

**Why this is not in ``app.pipeline``.** The pipeline is the composition module:
it imports the scoring worker, and the scoring worker imports ``aegis_ml``, which
the backend image does not install (D-075 records that split). The API process needs the
registry -- it is what turns an ``entity_id`` into a host or user value (T-416) --
and making ``app.main`` import the pipeline to get it would drag the ml worker
into the import graph of a service that is built without it. So the registry lives
here, in the service layer, with no imports of its own; ``app.pipeline`` imports it
from here and re-exports it for the callers that already know it by that name.
"""

from __future__ import annotations

__all__ = ["EntityRegistry"]


class EntityRegistry:
    """Assigns the integer id an alert row references (T-319).

    **The reverse direction is what makes an id renderable (T-416).** Every alert
    row carries an id and nothing else, so the overview's entity list -- and any
    other screen that has to name an entity -- asks this registry, and the id is
    the only key. :meth:`ref` answers with the ``(kind, value)`` pair or ``None``,
    and the endpoint says which of the two it got: an unnamed id is a fact about
    the deployment (a row written before the registry knew the entity, or by a
    process that never did), not a field the API forgot to fill.
    """

    __slots__ = ("_ids", "_refs")

    def __init__(self) -> None:
        """Start empty, with ids from 1 the way a fresh sequence would."""
        self._ids: dict[tuple[str, str], int] = {}
        self._refs: dict[int, tuple[str, str]] = {}

    def id_for(self, kind: str, value: str) -> int:
        """Return the stable id for one entity, allocating it on first sight."""
        key = (kind, value)
        if key not in self._ids:
            self._ids[key] = len(self._ids) + 1
            self._refs[self._ids[key]] = key
        return self._ids[key]

    def ref(self, entity_id: int) -> tuple[str, str] | None:
        """The ``(kind, value)`` an id stands for, or ``None`` if unknown."""
        return self._refs.get(entity_id)

    def entries(self) -> tuple[tuple[int, str, str], ...]:
        """Every known entity as ``(id, kind, value)``, ordered by id."""
        return tuple((id_, kind, value) for id_, (kind, value) in sorted(self._refs.items()))

    def __len__(self) -> int:
        """How many entities have been seen."""
        return len(self._ids)
