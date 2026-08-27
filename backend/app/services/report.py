"""Human-readable case report generator for the autonomous analyst.

Produces a self-contained markdown report capturing what happened, the blast
radius, the decision a human made, the (reversible) action taken, and the audit
trail references. Stored on ``case.report`` at decision time and served by the
report endpoint. Pure string assembly -- no I/O, no DB.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _fmt_ts(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M UTC")
    return str(value)


def _decision_line(decision: str) -> str:
    return {
        "approved": "APPROVED - the recommended action was authorized and recorded.",
        "declined": "DECLINED - no action was taken; the case was dismissed by a human.",
        "reverted": "REVERTED - a previously approved action was rolled back.",
        "pending": "PENDING - awaiting human decision.",
    }.get(decision, decision)


def build_case_report(case, analysis: dict, action: dict, decision: str, *, actor: str | None = None) -> str:
    """Build the markdown report for a decided analyst case."""
    analysis = analysis or {}
    action = action or {}
    rec = analysis.get("recommended_action") or {}
    blast = (case.blast_radius or {}) if getattr(case, "blast_radius", None) else {}
    nodes = blast.get("nodes") or []

    generated = _fmt_ts(datetime.now(timezone.utc))
    model = analysis.get("model") or "unknown"
    fallback = analysis.get("fallback")
    engine_note = f"{model}{' (templated fallback)' if fallback else ''}"

    lines: list[str] = []
    lines.append(f"# Case #{getattr(case, 'id', '?')} - {analysis.get('headline') or case.title}")
    lines.append("")
    lines.append(f"*Generated {generated} by AXIOM AI analyst ({engine_note}).*")
    lines.append("")

    lines.append("## Summary")
    lines.append(analysis.get("what_happened") or case.description or "-")
    lines.append("")
    lines.append(f"**Why it matters.** {analysis.get('why_it_matters') or '-'}")
    lines.append("")

    lines.append("## Blast radius")
    lines.append(analysis.get("blast_radius_summary") or "-")
    if nodes:
        lines.append("")
        lines.append("| Asset type | Value |")
        lines.append("| --- | --- |")
        for node in nodes:
            lines.append(f"| {node.get('entity_type', '-')} | {node.get('value', '-')} |")
    lines.append("")

    lines.append("## Decision")
    lines.append(_decision_line(decision))
    lines.append("")
    lines.append(f"- **Decided by:** {actor or getattr(case, 'decided_by_id', None) or '-'}")
    lines.append(f"- **Decided at:** {_fmt_ts(getattr(case, 'decided_at', None))}")
    lines.append("")

    lines.append("## Action")
    action_type = action.get("action_type") or rec.get("action_type") or "-"
    target = action.get("target") or rec.get("target") or "-"
    undo = action.get("undo") or rec.get("undo") or "-"
    lines.append(f"- **Action:** `{action_type}`")
    lines.append(f"- **Target:** {target}")
    lines.append(f"- **Rationale:** {rec.get('rationale') or '-'}")
    lines.append(f"- **Reversible via:** {undo}")
    soar_id = getattr(case, "soar_action_id", None)
    if soar_id:
        lines.append(f"- **SOAR action id:** `{soar_id}`")
    lines.append("")

    lines.append("## Audit trail")
    lines.append(
        "This case and its decision are recorded in the append-only audit log "
        "(`ANALYST_CASE_OPENED`, and one of `ANALYST_CASE_APPROVED` / "
        "`ANALYST_CASE_DECLINED` / `ANALYST_CASE_REVERTED`)."
    )
    lines.append("")

    return "\n".join(lines)
