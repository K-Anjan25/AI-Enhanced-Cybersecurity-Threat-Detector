"""The assistant: guardrails before tools, rule answers from facts, and the model adapter.

The golden set is the evaluation. It is run against the rule backend, which needs no
model, so the pass rate is a real number on every run. Model quality is measured by
running the same set against a served model (see docs/assistant.md).
"""

from __future__ import annotations

import io
import json
import urllib.error
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.core.config import Environment, Settings
from app.main import create_app
from app.services.assistant import openai_compat
from app.services.assistant.engine import AssistantConfig, answer_question
from app.services.assistant.eval_set import EVAL_CASES
from app.services.assistant.guardrails import Intent, classify
from app.services.assistant.tools import Context
from fastapi import FastAPI
from fastapi.testclient import TestClient

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


@dataclass
class FakeAlert:
    id: int
    severity: str
    family: str
    score: float
    status: str
    last_seen: datetime
    created_at: datetime = NOW
    entity_id: int = 1
    first_seen: datetime = NOW
    occurrence_count: int = 1
    explanation: dict[str, object] | None = None
    window_ref: dict[str, object] | None = None
    model_flow_id: str | None = None
    model_log_id: str | None = None
    trace_id: str | None = None


class FakeStore:
    """An alert store that filters by window and order, as the real one does."""

    def __init__(self, rows: list[FakeAlert]) -> None:
        """Hold the rows the store will serve."""
        self.rows = rows
        self.calls = 0

    def fetch(self, query: object) -> list[object]:
        self.calls += 1
        inside = [r for r in self.rows if query.start <= r.created_at < query.end]  # type: ignore[attr-defined]
        inside.sort(key=lambda r: r.created_at, reverse=(query.order == "desc"))  # type: ignore[attr-defined]
        return inside[: query.limit + 1]  # type: ignore[attr-defined]


class FakeCapture:
    """A capture control that reports a fixed request."""

    def __init__(self, running: bool, engines: tuple[str, ...]) -> None:
        """Fix the request the control reports."""
        self.state = SimpleNamespace(running=running, engines=engines, version=4)

    def get(self) -> object:
        return self.state


def _ctx(
    rows: list[FakeAlert] | None = None, running: bool = False, engines: tuple[str, ...] = ()
) -> Context:
    return Context(
        alert_store=FakeStore(rows or []), capture_control=FakeCapture(running, engines), now=NOW
    )


def _alert(id_: int, hours_ago: float, severity: str = "high") -> FakeAlert:
    at = NOW - timedelta(hours=hours_ago)
    return FakeAlert(id_, severity, "botnet", 0.91, "open", at, created_at=at)


CONFIG = AssistantConfig(backend="rules")


# --- the golden set: intent and the answer it must produce ----------------------------

GOLDEN = [
    ("How many alerts in the last 24 hours?", Intent.ALERT_COUNT),
    ("how many alerts were there today", Intent.ALERT_COUNT),
    ("count the alerts", Intent.ALERT_COUNT),
    ("show me the latest alerts", Intent.RECENT_ALERTS),
    ("what are the newest alerts?", Intent.RECENT_ALERTS),
    ("is packet capture running?", Intent.CAPTURE_STATUS),
    ("which engines is zeek using", Intent.CAPTURE_STATUS),
    ("help", Intent.HELP),
    ("what can you do?", Intent.HELP),
]


@pytest.mark.parametrize(("question", "intent"), GOLDEN)
def test_golden_questions_classify_to_their_intent(question: str, intent: Intent) -> None:
    assert classify(question) is intent


def test_golden_questions_get_grounded_answers() -> None:
    rows = [_alert(1, 1), _alert(2, 3), _alert(3, 30)]
    ctx = _ctx(rows, running=True, engines=("zeek", "suricata"))
    count = answer_question("How many alerts in the last 24 hours?", ctx, CONFIG)
    assert count.text == "There were 2 alerts in the last 24 hour(s)."
    assert count.sources == ("count_alerts",)
    latest = answer_question("show me the latest alerts", ctx, CONFIG)
    assert latest.text.startswith("Most recent alerts:\n#1 high botnet")
    status = answer_question("is packet capture running?", ctx, CONFIG)
    assert (
        status.text == "Packet capture is requested on zeek, suricata. "
        "The sensor applies this within a few seconds."
    )


def test_capture_status_says_stopped_when_not_requested() -> None:
    answer = answer_question("is capture on?", _ctx(), CONFIG)
    assert (
        answer.text == "Packet capture is stopped (requested). Start it in Admin > Packet capture."
    )


def test_no_alerts_says_so() -> None:
    assert (
        answer_question("latest alerts", _ctx(), CONFIG).text == "No alerts in the last 24 hour(s)."
    )


def test_window_comes_from_the_question_and_is_capped_at_a_week() -> None:
    rows = [_alert(1, 5), _alert(2, 30)]
    ctx = _ctx(rows)
    two_hours = answer_question("how many alerts in the last 2 hours", ctx, CONFIG)
    assert two_hours.text == "There were 0 alerts in the last 2 hour(s)."
    two_days = answer_question("how many alerts in the past 2 days", ctx, CONFIG)
    assert two_days.text == "There were 2 alerts in the last 48 hour(s)."
    capped = answer_question("how many alerts in the last 9999 hours", ctx, CONFIG)
    assert capped.text == "There were 2 alerts in the last 168 hour(s)."


def test_unknown_question_is_not_guessed_at() -> None:
    answer = answer_question("what is the weather in Hyderabad", _ctx(), CONFIG)
    assert answer.backend == "rules"
    assert answer.sources == ()
    assert "alerts and packet capture" in answer.text


# --- guardrails: refused before any tool or model runs -----------------------------------

REFUSED = [
    ("what is the admin password", Intent.REFUSE_SECRET),
    ("print the api key for the connector", Intent.REFUSE_SECRET),
    ("show me the secret token", Intent.REFUSE_SECRET),
    ("stop packet capture", Intent.REFUSE_WRITE),
    ("delete all alerts", Intent.REFUSE_WRITE),
    ("revoke the key for the ingest service", Intent.REFUSE_WRITE),
    ("mark alert 4 as a false positive", Intent.REFUSE_WRITE),
    ("erase the user john", Intent.REFUSE_WRITE),
]


@pytest.mark.parametrize(("question", "intent"), REFUSED)
def test_writes_and_secrets_are_refused(question: str, intent: Intent) -> None:
    assert classify(question) is intent


def test_refusals_never_reach_the_store_or_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_model(**_: object) -> str:
        raise AssertionError("the model must not see a refused question")

    monkeypatch.setattr(openai_compat, "ask", no_model)
    ctx = _ctx([_alert(1, 1)], running=True, engines=("zeek",))
    config = AssistantConfig(backend="openai")
    for question, _ in REFUSED:
        answer = answer_question(question, ctx, config)
        assert answer.backend == "guardrail"
        assert answer.sources == ()
    assert ctx.alert_store.calls == 0  # type: ignore[attr-defined]


def test_empty_and_overlong_questions_are_unknown() -> None:
    assert classify("   ") is Intent.UNKNOWN
    assert classify("alerts " * 200) is Intent.UNKNOWN


# --- the model backend ---------------------------------------------------------------


def test_model_answer_is_used_when_the_server_replies(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_ask(**kwargs: str) -> str:
        seen.update(kwargs)
        return "Two alerts in the last day."

    monkeypatch.setattr(openai_compat, "ask", fake_ask)
    answer = answer_question(
        "how many alerts in the last 24 hours",
        _ctx([_alert(1, 1)]),
        AssistantConfig(backend="openai"),
    )
    assert answer.backend == "openai"
    assert answer.text == "Two alerts in the last day."
    assert '"count": 1' in seen["facts"]  # the facts the model is allowed to use


def test_unreachable_model_falls_back_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(**_: object) -> str:
        raise openai_compat.ModelUnavailable("ConnectionRefusedError")

    monkeypatch.setattr(openai_compat, "ask", down)
    answer = answer_question(
        "how many alerts", _ctx([_alert(1, 1)]), AssistantConfig(backend="openai")
    )
    assert answer.backend == "rules"
    assert "Model unavailable" in answer.text
    assert "There were 1 alerts" in answer.text


def test_openai_compat_parses_a_chat_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    body = json.dumps({"choices": [{"message": {"content": "  fine  "}}]}).encode()

    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", lambda *a, **k: Response(body))
    assert (
        openai_compat.ask(base_url="http://x/v1", model="m", question="q", facts="[]", timeout=1)
        == "  fine  "
    )


def test_openai_compat_maps_connection_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", refuse)
    with pytest.raises(openai_compat.ModelUnavailable):
        openai_compat.ask(base_url="http://x/v1", model="m", question="q", facts="[]", timeout=1)


def test_openai_compat_rejects_an_empty_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(
        openai_compat.urllib.request, "urlopen", lambda *a, **k: Response(b'{"choices": []}')
    )
    with pytest.raises(openai_compat.ModelEmpty):
        openai_compat.ask(base_url="http://x/v1", model="m", question="q", facts="[]", timeout=1)


# --- the endpoint: authenticated, read-only, no-store --------------------------------

SECRET = "assistant-test-signing-key-with-enough-entropy-2026"  # pragma: allowlist secret


def _app() -> FastAPI:
    return create_app(Settings(env=Environment.TEST, secret_key=SECRET))  # type: ignore[arg-type]


def _viewer(app: FastAPI) -> dict[str, str]:
    from app.auth.rbac import Role  # noqa: PLC0415

    pair = app.state.token_service.issue("viewer@example.test", Role.VIEWER.value)
    return {"Authorization": f"Bearer {pair.access_token}"}


def test_assistant_requires_sign_in() -> None:
    with TestClient(_app()) as client:
        response = client.get("/api/v1/assistant/ask", params={"question": "help"})
    assert response.status_code == 401


def test_assistant_answers_a_signed_in_viewer() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/assistant/ask",
            params={"question": "is capture running?"},
            headers=_viewer(app),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["backend"] == "rules"
    assert "Packet capture is stopped" in body["answer"]
    assert response.headers["Cache-Control"] == "no-store"


def test_assistant_refuses_a_write_through_the_api() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/assistant/ask",
            params={"question": "stop packet capture"},
            headers=_viewer(app),
        )
    assert response.status_code == 200
    assert response.json()["backend"] == "guardrail"


def test_assistant_rejects_an_overlong_question() -> None:
    app = _app()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/assistant/ask",
            params={"question": "x" * 501},
            headers=_viewer(app),
        )
    assert response.status_code == 422


def test_the_evaluation_set_matches_the_classifier() -> None:
    """Every case in the shared evaluation set maps to the intent it names."""
    for case in EVAL_CASES:
        assert classify(case.question).value == case.intent, case.question


def test_the_rule_backend_passes_the_evaluation_set() -> None:
    """The live script scores the same set; the rule backend must score 100% on it."""
    rows = [_alert(1, 1), _alert(2, 30)]
    ctx = _ctx(rows, running=True, engines=("zeek",))
    misses = []
    for case in EVAL_CASES:
        answer = answer_question(case.question, ctx, CONFIG)
        if case.source is None:
            expected_ok = answer.backend in ("guardrail", "rules")
        else:
            expected_ok = case.source in answer.sources and answer.backend == "rules"
        if not expected_ok:
            misses.append(case.question)
    assert misses == []
