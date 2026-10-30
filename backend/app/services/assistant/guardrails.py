"""Classify a question before anything reads data or calls a model.

The classifier is deliberately conservative: a question it does not recognise is
answered with the list of things the assistant can do, never guessed at.
"""

from __future__ import annotations

import re
from enum import StrEnum

MAX_QUESTION_CHARS = 500


class Intent(StrEnum):
    """What a question is asking for. Refusals are intents too, so they are tested like answers."""

    ALERT_COUNT = "alert_count"
    RECENT_ALERTS = "recent_alerts"
    CAPTURE_STATUS = "capture_status"
    HELP = "help"
    REFUSE_SECRET = "refuse_secret"  # noqa: S105 - an intent name, not a credential
    REFUSE_WRITE = "refuse_write"
    UNKNOWN = "unknown"


_SECRET = re.compile(
    r"\b(password|passwd|secret|token|api[\s_-]?key|credential|private key)s?\b", re.I
)
_WRITE = re.compile(
    r"\b(stop|start|delete|remove|revoke|erase|disable|enable|create|reset|change|update|"
    r"approve|close|resolve|mark|verdict|grant|promote|rollback|roll back|issue|set)\b",
    re.I,
)
_COUNT = re.compile(r"\bhow many\b|\bcount\b|\bnumber of\b", re.I)
_RECENT = re.compile(
    r"\b(recent|latest|last|newest|show|list)\b.*\balerts?\b|\balerts?\b.*\b(recent|latest|newest)\b",
    re.I,
)
_CAPTURE = re.compile(r"\bcapture\b|\bsensor\b|\bzeek\b|\bsuricata\b|\btshark\b", re.I)
_HELP = re.compile(r"^\s*(help|what can you do|hi|hello)\b", re.I)
_ALERT = re.compile(r"\balerts?\b", re.I)
_WINDOW = re.compile(r"\b(?:last|past)\s+(\d{1,4})\s*(hours?|hrs?|h|days?|weeks?)\b", re.I)
DEFAULT_WINDOW_HOURS = 24


def window_hours(question: str) -> int:
    """The window the question names, in hours. Defaults to 24; the tools cap it at a week."""
    match = _WINDOW.search(question)
    if not match:
        return DEFAULT_WINDOW_HOURS
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("day"):
        return amount * 24
    if unit.startswith("week"):
        return amount * 168
    return amount


def classify(question: str) -> Intent:
    """Return the intent, with refusals first. Empty or overlong input is unknown."""
    text = question.strip()
    if not text or len(text) > MAX_QUESTION_CHARS:
        return Intent.UNKNOWN
    if _SECRET.search(text):
        return Intent.REFUSE_SECRET
    if _WRITE.search(text):
        return Intent.REFUSE_WRITE
    if _HELP.search(text):
        return Intent.HELP
    if _CAPTURE.search(text) and not _ALERT.search(text):
        return Intent.CAPTURE_STATUS
    if _ALERT.search(text) and _COUNT.search(text):
        return Intent.ALERT_COUNT
    if _ALERT.search(text) and _RECENT.search(text):
        return Intent.RECENT_ALERTS
    return Intent.UNKNOWN


REFUSALS: dict[Intent, str] = {
    Intent.REFUSE_SECRET: (
        "I can't help with passwords, tokens, keys or other secrets. Those are managed in "
        "Admin > API keys and Admin > Connectors."
    ),
    Intent.REFUSE_WRITE: (
        "I can only read alerts and capture status. To change something, use the screen for "
        "it: Admin > Packet capture to start or stop capture, Alerts to record a verdict."
    ),
}

HELP_TEXT = (
    "I can answer: how many alerts there were in the last N hours, what the most recent "
    "alerts are, and whether packet capture is requested and on which engines."
)
