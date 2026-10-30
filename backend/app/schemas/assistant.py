"""Assistant wire shapes. Checked against the dashboard's types."""

from __future__ import annotations

from pydantic import BaseModel


class AskOut(BaseModel):
    """The answer, which backend produced it, and which read-only tools supplied facts."""

    answer: str
    backend: str
    sources: list[str]
