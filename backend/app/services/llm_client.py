"""LLM reasoning client for the autonomous analyst (Anthropic Messages API).

Mirrors the resilience contract of ``ml_client.py``: synchronous ``requests``
with retry + exponential backoff, and a deterministic **templated fallback** so
the product loop (sense -> reason -> propose -> approve -> report) works
end-to-end even with **no API key**. ``analyze_incident`` never raises.

Analysis JSON contract (both the live and fallback paths return this shape)::

    {
      "headline": str,
      "what_happened": str,
      "why_it_matters": str,
      "blast_radius_summary": str,
      "recommended_action": {
        "action_type": <one of soar.SUPPORTED_ACTIONS>,
        "target": str,
        "rationale": str,
        "undo": str
      },
      "confidence": float,   # 0..1
      "model": str,
      "fallback": bool
    }
"""

from __future__ import annotations

import json
import time

import requests

from app.core.config import settings
from app.services.soar import SUPPORTED_ACTIONS

_ANTHROPIC_VERSION = "2023-06-01"

# Human-readable "how to undo this" text per supported action. Kept here so both
# the live and fallback narratives describe a reversible step honestly.
_UNDO_TEXT = {
    "REVOKE_CREDENTIALS": "Re-enable the account and force a password reset once the owner is verified.",
    "DISABLE_ACCOUNT": "Re-enable the account from the identity provider once verified.",
    "BLOCK_SOURCE_IP": "Remove the IP from the blocklist if it turns out to be legitimate.",
    "QUARANTINE_ENDPOINT": "Release the endpoint from quarantine after it is scanned clean.",
    "ALERT_OPERATOR": "No system change was made; dismiss the notification if not needed.",
    "REVIEW_ONLY": "No change was made; close the review if benign.",
}

_CONFIDENCE_BY_SEVERITY = {
    "CRITICAL": 0.9,
    "HIGH": 0.8,
    "MEDIUM": 0.6,
    "LOW": 0.4,
}


def _post_with_retry(url: str, json_body: dict, headers: dict, timeout: float, max_retries: int = 2) -> dict:
    """POST with retries + exponential backoff. Raises ConnectionError on give-up."""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, json=json_body, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - network errors are expected
            last_error = exc
            if attempt < max_retries:
                time.sleep(0.3 * (2 ** attempt))
    raise requests.ConnectionError(f"LLM service unreachable after {max_retries + 1} attempts: {last_error}")


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are NOCTRA, an autonomous security analyst working for a growing company "
    "that needs instant threat reasoning and blast-radius assessment. You are given "
    "one security incident and its blast radius (the connected assets it touches). "
    "Explain it calmly in plain English for a non-expert owner, and recommend ONE reversible response.\n\n"
    "Reply with ONLY a single JSON object (no prose, no markdown fences) with EXACTLY "
    "these keys:\n"
    '  "headline": a short one-line summary (<= 90 chars)\n'
    '  "what_happened": 1-3 plain-English sentences\n'
    '  "why_it_matters": 1-2 sentences on business impact\n'
    '  "blast_radius_summary": 1-2 sentences on what could be affected\n'
    '  "recommended_action": { "action_type", "target", "rationale", "undo" }\n'
    '  "confidence": a number from 0 to 1\n'
    "The recommended_action.action_type MUST be exactly one of: "
    + ", ".join(sorted(SUPPORTED_ACTIONS))
    + ". Prefer the least-destructive action that contains the threat. "
    "The 'undo' field must describe how to reverse the action."
)


def _build_user_content(alert: dict, entities: list[dict]) -> str:
    lines = [
        "INCIDENT:",
        f"- type: {alert.get('alert_type')}",
        f"- severity: {alert.get('severity')}",
        f"- source_ip: {alert.get('source_ip')}",
        f"- mitre_technique_id: {alert.get('mitre_technique_id')}",
        f"- message: {alert.get('message')}",
        "",
        "BLAST RADIUS (connected assets):",
    ]
    if entities:
        for ent in entities:
            lines.append(f"- {ent.get('entity_type')}: {ent.get('value')}")
    else:
        lines.append("- (none mapped)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fallback (deterministic, no API key required)
# ---------------------------------------------------------------------------

def _pick_action(alert: dict, entities: list[dict]) -> tuple[str, str]:
    """Choose a supported action + target for the fallback narrative."""
    alert_type = (alert.get("alert_type") or "").lower()
    mitre = (alert.get("mitre_technique_id") or "").upper()
    severity = (alert.get("severity") or "").upper()

    # Prefer an account/email target when the incident is credential-related.
    account = next((e for e in entities if e.get("entity_type") in ("account", "email")), None)

    if "credential" in alert_type or mitre == "T1078":
        target = f"{account['entity_type']}:{account['value']}" if account else (alert.get("source_ip") or "unknown")
        return "REVOKE_CREDENTIALS", target
    if severity == "CRITICAL" and alert.get("source_ip"):
        return "BLOCK_SOURCE_IP", f"ip:{alert.get('source_ip')}"
    return "ALERT_OPERATOR", (alert.get("source_ip") or "operator")


def fallback_analyze(alert: dict, entities: list[dict]) -> dict:
    """Deterministic templated analysis so the demo is meaningful with no key."""
    entities = entities or []
    severity = (alert.get("severity") or "MEDIUM").upper()
    action_type, target = _pick_action(alert, entities)
    asset_values = ", ".join(e.get("value", "") for e in entities if e.get("value")) or "the affected account"

    if action_type == "REVOKE_CREDENTIALS":
        headline = "Leaked corporate credential is being used to sign in"
        what = (
            f"A set of company credentials appears to have leaked and is being used from "
            f"{alert.get('source_ip') or 'an external address'}. This matches the pattern of a "
            f"stolen-account sign-in (MITRE {alert.get('mitre_technique_id') or 'T1078'})."
        )
        why = (
            "A valid but stolen login lets an attacker act as a trusted employee, so it can "
            "quietly reach data and systems that employee could reach."
        )
    elif action_type == "BLOCK_SOURCE_IP":
        headline = f"Critical activity from {alert.get('source_ip') or 'an external IP'}"
        what = f"A critical-severity {alert.get('alert_type') or 'security'} event was raised from {alert.get('source_ip')}."
        why = "Critical events left unaddressed can escalate into a wider compromise."
    else:
        headline = f"{severity.title()} security event needs a look"
        what = f"A {severity.lower()} {alert.get('alert_type') or 'security'} event was raised: {alert.get('message') or 'see details'}."
        why = "It should be reviewed so nothing is missed, even if it turns out to be benign."

    return _coerce_analysis(
        {
            "headline": headline,
            "what_happened": what,
            "why_it_matters": why,
            "blast_radius_summary": f"Connected assets that could be reached: {asset_values}.",
            "recommended_action": {
                "action_type": action_type,
                "target": target,
                "rationale": "Contain the incident with the least-destructive reversible step, then verify with the owner.",
                "undo": _UNDO_TEXT.get(action_type, "Reverse the change once the activity is confirmed benign."),
            },
            "confidence": _CONFIDENCE_BY_SEVERITY.get(severity, 0.5),
        },
        model="fallback-template",
        fallback=True,
    )


# ---------------------------------------------------------------------------
# Contract normalization
# ---------------------------------------------------------------------------

def _coerce_analysis(raw: dict, *, model: str, fallback: bool) -> dict:
    """Force ``raw`` into the analysis contract, validating the action type."""
    raw = raw if isinstance(raw, dict) else {}
    action = raw.get("recommended_action")
    if not isinstance(action, dict):
        action = {}
    action_type = str(action.get("action_type") or "").upper()
    if action_type not in SUPPORTED_ACTIONS:
        action_type = "ALERT_OPERATOR"

    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    return {
        "headline": str(raw.get("headline") or "Security incident detected"),
        "what_happened": str(raw.get("what_happened") or ""),
        "why_it_matters": str(raw.get("why_it_matters") or ""),
        "blast_radius_summary": str(raw.get("blast_radius_summary") or ""),
        "recommended_action": {
            "action_type": action_type,
            "target": str(action.get("target") or "unknown"),
            "rationale": str(action.get("rationale") or ""),
            "undo": str(action.get("undo") or _UNDO_TEXT.get(action_type, "")),
        },
        "confidence": round(confidence, 3),
        "model": model,
        "fallback": fallback,
    }


def _extract_json(text: str) -> dict:
    """Best-effort parse of a JSON object from an LLM text response."""
    text = (text or "").strip()
    if text.startswith("```"):
        # Strip a leading ```json / ``` fence and the trailing fence.
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in LLM response")
    return json.loads(text[start : end + 1])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_incident(alert: dict, entities: list[dict]) -> dict:
    """Reason about one incident + its blast radius. Never raises.

    Uses the Anthropic Messages API when a key is configured and the LLM is
    enabled; otherwise (or on any error/parse failure) returns a deterministic
    templated analysis with ``fallback: True``.
    """
    entities = entities or []
    if not settings.LLM_ENABLED or not settings.ANTHROPIC_API_KEY:
        return fallback_analyze(alert, entities)

    url = f"{settings.ANTHROPIC_BASE_URL.rstrip('/')}/v1/messages"
    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": settings.ANTHROPIC_MODEL,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _build_user_content(alert, entities)}],
    }

    try:
        data = _post_with_retry(url, body, headers, timeout=settings.LLM_TIMEOUT)
        text = ""
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")
        parsed = _extract_json(text)
        return _coerce_analysis(parsed, model=settings.ANTHROPIC_MODEL, fallback=False)
    except Exception:  # noqa: BLE001 - any failure degrades to the templated path
        return fallback_analyze(alert, entities)
