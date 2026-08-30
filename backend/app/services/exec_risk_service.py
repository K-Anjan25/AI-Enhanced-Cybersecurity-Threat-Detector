"""Phase 72: Exec risk + board pack + ROI."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.exec_risk import RiskMetric, ExecReport, ROIMetric
from app.models import SecurityAlert, Case
from app.models.vuln import Vulnerability


def _now():
    return datetime.now(timezone.utc)


def calculate_risk_metrics(db: Session, org_id: int) -> List[RiskMetric]:
    """Calculate current risk metrics."""
    metrics = []

    # Count open high/critical alerts
    high_alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id, SecurityAlert.severity.in_(["HIGH", "CRITICAL"])).count()
    m1 = RiskMetric(org_id=org_id, metric_name="high_severity_alerts", metric_value=float(high_alerts), trend_json={"previous": high_alerts})
    db.add(m1)
    metrics.append(m1)

    # Response time, measured rather than asserted. This used to be the
    # literal `mttd = 2.5  # hours` — the number a buyer benchmarks against,
    # typed in by hand. It is now the observed median, recorded only when
    # there is a real sample behind it, and named for what it actually
    # measures: ingest to triage, not attacker-action to detection.
    from app.services import response_metrics

    timings = response_metrics.compute(db, org_id)
    triage = next(
        (m for m in timings["metrics"] if m["metric"] == "time_to_triage"), None
    )
    if triage and triage["median_minutes"] is not None:
        m2 = RiskMetric(
            org_id=org_id,
            metric_name="median_time_to_triage_minutes",
            metric_value=float(triage["median_minutes"]),
            trend_json={
                "sample_size": triage["sample_size"],
                "reliable": triage["reliable"],
                "measures": triage["measures"],
            },
        )
        db.add(m2)
        metrics.append(m2)

    # Vuln risk score avg
    vulns = db.query(Vulnerability).filter(Vulnerability.org_id == org_id).all()
    avg_risk = sum(v.risk_score or 0 for v in vulns) / max(1, len(vulns))
    m3 = RiskMetric(org_id=org_id, metric_name="avg_vuln_risk_score", metric_value=float(avg_risk))
    db.add(m3)
    metrics.append(m3)

    db.commit()
    for m in metrics:
        db.refresh(m)
    return metrics


def generate_board_pack(db: Session, org_id: int, generated_by_user_id: int = None) -> ExecReport:
    """Generate board pack report."""
    metrics = calculate_risk_metrics(db, org_id)
    open_cases = db.query(Case).filter(Case.org_id == org_id, Case.status != "closed").count()
    total_alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).count()

    from app.services import response_metrics

    timings = response_metrics.compute(db, org_id)

    report_data = {
        "executive_summary": f"Security posture: {open_cases} open cases, {total_alerts} total alerts.",
        "risk_trends": [{"metric_name": m.metric_name, "value": m.metric_value, "recorded_at": m.recorded_at.isoformat() if m.recorded_at else None} for m in metrics],
        "incidents": {"open_cases": open_cases, "total_alerts": total_alerts},
        # Measured response times replace the previous "roi" block, which
        # asserted 120 analyst hours saved, 65% auto-triaged and $50,000 of
        # cost avoidance. None of those three figures were computed from
        # anything — in a document addressed to a board.
        "response_times": timings,
        "not_measured": timings["not_measured"],
        "recommendations": ["Increase patching for critical vulns", "Review ZTNA policies", "Enable continuous compliance"],
    }

    report = ExecReport(org_id=org_id, title=f"Board Pack - {_now().date()}", report_type="board_pack", report_json=report_data, generated_by_user_id=generated_by_user_id)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def list_reports(db: Session, org_id: int) -> List[ExecReport]:
    return db.query(ExecReport).filter(ExecReport.org_id == org_id).order_by(ExecReport.created_at.desc()).all()


def calculate_roi(db: Session, org_id: int) -> Dict[str, Any]:
    """Report what can be counted, and name what cannot.

    This returned four hardcoded figures — 120 analyst hours saved, 45
    auto-triaged cases, 30 minutes saved per case, $50,000 cost avoidance —
    and persisted them as ROIMetric rows, so invented numbers accumulated a
    history that looked like evidence.

    Return on investment cannot be derived without a pre-automation baseline,
    which was never captured. What *is* countable is how many cases the system
    triaged on its own and how long decisions took.
    """
    from app.services import response_metrics

    auto_triaged = (
        db.query(Case)
        .filter(Case.org_id == org_id, Case.kind == "analyst")
        .count()
    )
    total_cases = db.query(Case).filter(Case.org_id == org_id).count()
    timings = response_metrics.compute(db, org_id)

    counted = [
        {"metric_name": "auto_triaged_cases", "value": auto_triaged, "unit": "cases"},
        {"metric_name": "total_cases", "value": total_cases, "unit": "cases"},
    ]
    for rm in counted:
        db.add(
            ROIMetric(
                org_id=org_id,
                metric_name=rm["metric_name"],
                value=float(rm["value"]),
                unit=rm["unit"],
            )
        )
    db.commit()

    return {
        "counted": counted,
        "auto_triaged_percent": (
            round(100.0 * auto_triaged / total_cases, 1) if total_cases else None
        ),
        "response_times": timings,
        "not_measured": timings["not_measured"],
    }


def serialize_report(r: ExecReport) -> Dict[str, Any]:
    return {"id": r.id, "title": r.title, "report_type": r.report_type, "report_json": r.report_json, "created_at": r.created_at.isoformat() if r.created_at else None}


def serialize_metric(m: RiskMetric) -> Dict[str, Any]:
    return {"id": m.id, "metric_name": m.metric_name, "metric_value": m.metric_value, "trend": m.trend_json, "recorded_at": m.recorded_at.isoformat() if m.recorded_at else None}
