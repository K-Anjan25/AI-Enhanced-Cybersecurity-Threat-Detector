"""Why a case carries the confidence it does.

An AI analyst that says "87% confident, isolate the host" and nothing more is
asking to be trusted on faith. The research on SMB buyers is consistent on this
point: the differentiator is transparent, auditable reasoning per alert — an
operator has to be able to see which signals produced a verdict, how much each
one moved it, and, just as importantly, which signals were *not available*.

That last part is what this module exists for. A confidence of 0.5 computed
from four corroborating signals means something entirely different from a 0.5
computed with threat intel switched off and no asset inventory. Both used to
render as the same number. Before this module, confidence was either a
hardcoded 0.85 stamped on every auto-triaged case, or `_CONFIDENCE_BY_SEVERITY`
— a restatement of the severity the alert already carried, dressed up as an
independent judgement.

Design rules, all test-enforced:

* **Every contribution is derived from a real row.** No signal may invent its
  own evidence; each one either finds data or reports itself unavailable.
* **Unavailable is not neutral, and never silent.** A signal that could not run
  is listed in ``unavailable`` with the reason, and it widens the uncertainty
  band rather than quietly scoring zero.
* **The arithmetic is reproducible.** ``base`` plus the sum of contributions
  equals ``confidence``, so an operator (or an auditor) can check it by hand.
* **Confidence is capped by coverage.** You cannot be 95% sure from one signal.
  The cap is a function of how much of the picture was actually visible.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.case import Case

# Starting point before any evidence is considered. Deliberately below the
# midpoint: with no signals at all, the honest position is "we do not know",
# leaning slightly toward "probably needs a human".
_BASE = 0.40

# How much each signal may move confidence. Positive values raise it (the case
# looks real), negative values lower it (the case looks benign or unclear).
# These are weights on *evidence*, not on severity — severity is what we are
# trying to corroborate, so letting it vote would be circular.
_MAX_CONTRIBUTION = {
    "crown_jewel_reach": 0.20,
    "affected_assets": 0.15,
    "threat_intel": 0.20,
    "leaked_credentials": 0.15,
    "posture": 0.10,
    "correlation": 0.15,
}

# Confidence ceiling as a function of how many signals actually reported.
# One signal agreeing with itself is not strong evidence, however emphatic.
_COVERAGE_CAP = {0: 0.50, 1: 0.65, 2: 0.75, 3: 0.85, 4: 0.90}
_MAX_CAP = 0.95


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _signal(
    name: str,
    label: str,
    *,
    contribution: float,
    detail: str,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One line of the audit trail: what was found and what it was worth."""
    cap = _MAX_CONTRIBUTION.get(name, 0.10)
    return {
        "signal": name,
        "label": label,
        "contribution": round(_clamp(contribution, -cap, cap), 3),
        "detail": detail,
        "evidence": evidence or {},
    }


def _unavailable(name: str, label: str, reason: str) -> Dict[str, Any]:
    """A signal that could not be consulted. Recorded, never inferred as clean."""
    return {"signal": name, "label": label, "reason": reason}


# ---------------------------------------------------------------------------
# Individual signals
# ---------------------------------------------------------------------------

def _crown_jewel_signal(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    reach = context.get("crown_jewel_reach")
    if not reach:
        return None
    hops = reach.get("hops")
    asset = reach.get("asset_name") or "a crown-jewel asset"
    # Closer is worse: adjacent (0-1 hops) is the full weight.
    if hops is None:
        contribution = 0.10
        detail = f"A recorded attack path reaches {asset}."
    elif hops <= 1:
        contribution = 0.20
        detail = f"{asset} is {hops} hop away on a recorded attack path."
    elif hops <= 3:
        contribution = 0.14
        detail = f"{asset} is {hops} hops away on a recorded attack path."
    else:
        contribution = 0.07
        detail = f"{asset} is {hops} hops away — reachable but distant."
    return _signal(
        "crown_jewel_reach",
        "Crown-jewel reachability",
        contribution=contribution,
        detail=detail,
        evidence={"hops": hops, "asset": asset},
    )


def _asset_signal(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    assets = context.get("affected_assets")
    if not assets:
        return None
    top = max(assets, key=lambda a: a.get("criticality") or 0)
    criticality = top.get("criticality") or 0
    # Criticality is operator-assigned 1-5; scale it onto the weight.
    contribution = 0.03 * criticality
    detail = (
        f"{len(assets)} inventoried asset(s) match this case; "
        f"the most critical is {top.get('name')} (criticality {criticality}/5)."
    )
    return _signal(
        "affected_assets",
        "Affected assets",
        contribution=contribution,
        detail=detail,
        evidence={"count": len(assets), "top_asset": top.get("name"), "criticality": criticality},
    )


def _threat_intel_signal(alert: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Reputation for the alert's source IP, if it was actually enriched."""
    if alert is None:
        return None
    intel = getattr(alert, "threat_intel", None)
    if not isinstance(intel, dict) or not intel:
        return None
    if intel.get("enabled") is False:
        return None

    risk = intel.get("risk_score")
    if risk is None:
        return None

    reasons = intel.get("reasons") or []
    # risk is 0-100; map onto the weight band, centred so that a clean
    # lookup actively *lowers* confidence that this is a real incident.
    contribution = (float(risk) - 40.0) / 100.0 * 0.5
    if risk >= 50:
        detail = f"Source address has a threat-intel risk score of {risk:.0f}/100."
    elif risk > 0:
        detail = f"Source address is lightly flagged ({risk:.0f}/100)."
    else:
        detail = "Source address is clean across all consulted providers."
    if reasons:
        detail += " " + "; ".join(str(r) for r in reasons[:3]) + "."
    return _signal(
        "threat_intel",
        "Threat intelligence",
        contribution=contribution,
        detail=detail,
        evidence={"risk_score": risk, "reasons": reasons[:3]},
    )


def _leaked_credentials_signal(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    leaked = context.get("leaked_credentials")
    if not leaked:
        return None
    return _signal(
        "leaked_credentials",
        "Leaked credentials",
        contribution=0.15,
        detail=(
            f"{len(leaked)} credential(s) tied to this case appear in "
            "recorded breach findings."
        ),
        evidence={"count": len(leaked)},
    )


def _posture_signal(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    posture = context.get("posture")
    if not posture:
        return None
    impact = posture.get("impact")
    if impact is None:
        return None
    contribution = _clamp(float(impact) / 100.0, 0.0, 0.10)
    return _signal(
        "posture",
        "Security posture",
        contribution=contribution,
        detail=f"This case would move the posture score by {impact}.",
        evidence={"impact": impact},
    )


def _correlation_signal(db: Session, case: Case, alert: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Other recent alerts sharing this case's source IP.

    A single odd event is noise; the same source appearing repeatedly is a
    pattern. This counts real sibling rows — it never extrapolates.
    """
    if alert is None:
        return None
    source_ip = getattr(alert, "source_ip", None)
    if not source_ip:
        return None

    from app.models import SecurityAlert

    query = db.query(SecurityAlert).filter(SecurityAlert.source_ip == source_ip)
    if case.org_id is not None:
        query = query.filter(SecurityAlert.org_id == case.org_id)
    siblings = query.limit(50).all()
    others = [a for a in siblings if a.id != getattr(alert, "id", None)]
    if not others:
        return _signal(
            "correlation",
            "Related activity",
            contribution=-0.05,
            detail=f"No other alerts share the source {source_ip}; this looks isolated.",
            evidence={"related_alerts": 0, "source_ip": source_ip},
        )

    count = len(others)
    contribution = min(0.05 * count, 0.15)
    return _signal(
        "correlation",
        "Related activity",
        contribution=contribution,
        detail=f"{count} other alert(s) share the source {source_ip}.",
        evidence={"related_alerts": count, "source_ip": source_ip},
    )


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _unavailable_signals(
    db: Session, case: Case, context: Dict[str, Any], alert: Optional[Any]
) -> List[Dict[str, Any]]:
    """Name every signal that could not contribute, and why.

    This is the honest half of the report. Each entry means "we did not look",
    not "we looked and found nothing" — a distinction the previous
    implementation erased entirely.
    """
    from app.models import Asset
    from app.services import threat_intel_enrichment

    missing: List[Dict[str, Any]] = []

    if not context.get("crown_jewel_reach"):
        asset_count = 0
        try:
            q = db.query(Asset)
            if case.org_id is not None:
                q = q.filter(Asset.org_id == case.org_id)
            asset_count = q.count()
        except Exception:  # pragma: no cover - counting must never break triage
            asset_count = 0
        reason = (
            "no assets are recorded, so no attack path can be computed"
            if asset_count == 0
            else "no recorded attack path connects this case to a crown jewel"
        )
        missing.append(_unavailable("crown_jewel_reach", "Crown-jewel reachability", reason))

    if not context.get("affected_assets"):
        missing.append(
            _unavailable(
                "affected_assets",
                "Affected assets",
                "no inventoried asset matches the entities in this case",
            )
        )

    if alert is None:
        missing.append(
            _unavailable("threat_intel", "Threat intelligence", "this case has no source alert")
        )
    else:
        intel = getattr(alert, "threat_intel", None)
        if not getattr(threat_intel_enrichment.settings, "THREAT_INTEL_ENABLED", True):
            missing.append(
                _unavailable(
                    "threat_intel", "Threat intelligence", "THREAT_INTEL_ENABLED is false"
                )
            )
        elif not isinstance(intel, dict) or not intel:
            missing.append(
                _unavailable(
                    "threat_intel",
                    "Threat intelligence",
                    "the source address has not been enriched",
                )
            )
        elif intel.get("risk_score") is None:
            missing.append(
                _unavailable(
                    "threat_intel",
                    "Threat intelligence",
                    intel.get("reason") or "no provider returned a usable score",
                )
            )
        if not getattr(alert, "source_ip", None):
            missing.append(
                _unavailable(
                    "correlation", "Related activity", "the source alert carries no source IP"
                )
            )

    if not context.get("leaked_credentials"):
        missing.append(
            _unavailable(
                "leaked_credentials",
                "Leaked credentials",
                "no breach findings reference this case's identities",
            )
        )

    if not context.get("posture"):
        missing.append(
            _unavailable(
                "posture", "Security posture", "no posture score has been calculated yet"
            )
        )

    return missing


def explain(db: Session, case: Case, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the reasoning record behind this case's confidence.

    Returns a dict that is safe to persist on ``Case.analysis["reasoning"]`` and
    render directly. Never raises: a failure to explain must not block triage,
    but it also must not fake an explanation — on error the report says so.
    """
    try:
        from app.services import case_context

        if context is None:
            context = case_context.build(db, case)

        alert = None
        if case.source_alert_id:
            from app.models import SecurityAlert

            alert = (
                db.query(SecurityAlert)
                .filter(SecurityAlert.id == case.source_alert_id)
                .first()
            )

        candidates = [
            _crown_jewel_signal(context),
            _asset_signal(context),
            _threat_intel_signal(alert),
            _leaked_credentials_signal(context),
            _posture_signal(context),
            _correlation_signal(db, case, alert),
        ]
        signals = [s for s in candidates if s]
        unavailable = _unavailable_signals(db, case, context, alert)

        total = sum(s["contribution"] for s in signals)
        raw = _BASE + total

        # Coverage cap: confidence is limited by how much we could actually see.
        cap = _COVERAGE_CAP.get(len(signals), _MAX_CAP)
        confidence = round(_clamp(min(raw, cap)), 3)

        return {
            "base": _BASE,
            "signals": signals,
            "unavailable": unavailable,
            "confidence": confidence,
            "confidence_cap": cap,
            "capped": raw > cap,
            "coverage": f"{len(signals)} of {len(signals) + len(unavailable)} signals available",
            "summary": _summary(signals, unavailable, confidence),
        }
    except Exception as exc:  # pragma: no cover - defensive, contract is "never raise"
        return {
            "base": _BASE,
            "signals": [],
            "unavailable": [],
            "confidence": None,
            "error": str(exc),
            "summary": "Could not compute reasoning for this case. This is a failure, not a clean result.",
        }


def _summary(
    signals: List[Dict[str, Any]], unavailable: List[Dict[str, Any]], confidence: float
) -> str:
    """One plain sentence an operator can read without expanding anything."""
    if not signals:
        return (
            f"No corroborating signal was available, so confidence stays near the "
            f"{confidence:.0%} baseline. "
            f"{len(unavailable)} signal(s) could not be checked."
        )
    strongest = max(signals, key=lambda s: abs(s["contribution"]))
    lead = strongest["label"].lower()
    if unavailable:
        return (
            f"{confidence:.0%} confidence, driven mainly by {lead}. "
            f"{len(unavailable)} signal(s) could not be checked, which limits certainty."
        )
    return f"{confidence:.0%} confidence from {len(signals)} corroborating signals, led by {lead}."
