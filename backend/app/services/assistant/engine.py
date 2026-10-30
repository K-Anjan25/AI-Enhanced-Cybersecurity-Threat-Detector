"""Answer a question: guardrails, then tools, then a rule answer or a model answer."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.services.assistant import openai_compat
from app.services.assistant.guardrails import HELP_TEXT, REFUSALS, Intent, classify, window_hours
from app.services.assistant.tools import (
    Context,
    ToolResult,
    capture_status,
    count_alerts,
    recent_alerts,
)


@dataclass(frozen=True)
class AssistantConfig:
    """Which backend answers, and where the model server is. Read from settings per request."""

    backend: str = "rules"  # "rules" or "openai"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5:1.5b"
    timeout_seconds: float = 20.0


@dataclass(frozen=True)
class Answer:
    """An answer, the backend that produced it, and the tools that supplied facts."""

    text: str
    backend: str  # the backend that actually produced the text
    sources: tuple[str, ...]


def _rules_answer(intent: Intent, results: list[ToolResult]) -> str:
    by_name = {result.name: result for result in results}
    if intent is Intent.HELP:
        return HELP_TEXT
    if intent is Intent.ALERT_COUNT:
        result = by_name["count_alerts"]
        if result.error:
            return f"I could not count alerts: {result.error}"
        count = result.facts["count"]
        hours = result.facts["hours"]
        qualifier = "at least " if result.facts["at_least"] else ""
        return f"There were {qualifier}{count} alerts in the last {hours} hour(s)."
    if intent is Intent.RECENT_ALERTS:
        result = by_name["recent_alerts"]
        if result.error:
            return f"I could not list alerts: {result.error}"
        alerts = result.facts["alerts"]
        if not alerts:
            return f"No alerts in the last {result.facts['hours']} hour(s)."
        lines = [
            f"#{a['id']} {a['severity']} {a['family']} (score {a['score']}, {a['status']})"
            for a in alerts  # type: ignore[union-attr]
        ]
        return "Most recent alerts:\n" + "\n".join(lines)
    if intent is Intent.CAPTURE_STATUS:
        facts = by_name["capture_status"].facts
        if not facts["requested"]:
            return "Packet capture is stopped (requested). Start it in Admin > Packet capture."
        engines = ", ".join(facts["engines"]) or "no engines"  # type: ignore[arg-type]
        return (
            f"Packet capture is requested on {engines}. "
            "The sensor applies this within a few seconds."
        )
    return (
        "I can answer questions about alerts and packet capture. "
        "Try: how many alerts in the last 24 hours?"
    )


def _run_tools(intent: Intent, ctx: Context, question: str) -> list[ToolResult]:
    hours = window_hours(question)
    if intent is Intent.ALERT_COUNT:
        return [count_alerts(ctx, hours=hours)]
    if intent is Intent.RECENT_ALERTS:
        return [recent_alerts(ctx, hours=hours, limit=5)]
    if intent is Intent.CAPTURE_STATUS:
        return [capture_status(ctx)]
    return []


def _model_answer(config: AssistantConfig, question: str, results: list[ToolResult]) -> str:
    facts = json.dumps([{"tool": r.name, "facts": r.facts, "error": r.error} for r in results])
    return openai_compat.ask(
        base_url=config.base_url,
        model=config.model,
        question=question,
        facts=facts,
        timeout=config.timeout_seconds,
    )


def answer_question(question: str, ctx: Context, config: AssistantConfig) -> Answer:
    """Answer one question. Refusals and unknown questions never reach a tool or model."""
    intent = classify(question)
    if intent in REFUSALS:
        return Answer(REFUSALS[intent], backend="guardrail", sources=())
    results = _run_tools(intent, ctx, question)
    sources = tuple(result.name for result in results)
    rules_text = _rules_answer(intent, results)
    if config.backend != "openai" or not results:
        return Answer(rules_text, backend="rules", sources=sources)
    try:
        text = _model_answer(config, question, results).strip()
    except (openai_compat.ModelUnavailable, openai_compat.ModelEmpty) as exc:
        return Answer(
            f"{rules_text}\n\n(Model unavailable, so this is the rule-based answer: {exc}.)",
            backend="rules",
            sources=sources,
        )
    if not text:
        return Answer(rules_text, backend="rules", sources=sources)
    return Answer(text, backend="openai", sources=sources)
