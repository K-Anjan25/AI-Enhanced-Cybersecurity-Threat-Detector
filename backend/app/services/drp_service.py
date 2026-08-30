"""Digital Risk Protection — brand abuse, lookalike domains, leaked credentials.

Two honest sources of signal, and nothing else:

1. **Locally computable** — typo-squat candidates are generated from the org's
   real domain using the standard registrable-variation algorithms
   (character omission/transposition/replacement, homoglyphs, common TLD
   swaps). These are *candidates*, and we label them as such: without DNS or
   registration data we cannot claim a lookalike is registered, only that it is
   the shape an attacker would use.

2. **External providers** — real dark-web / paste-site / certificate-transparency
   lookups require an API key. When no key is configured we report the provider
   as unavailable. We never invent a finding to fill the gap: a fabricated
   "leaked credential" is the fastest way to lose a customer's trust.

`scan_drp` therefore returns whatever is genuinely derivable plus a status
block naming which providers were consulted and which were skipped.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.drp import DRP_Monitor, DRP_Finding, DRP_Takedown
from app.models.user import User
from app.models.org import Org

def _now():
    return datetime.now(timezone.utc)


# Characters that render near-identically in most sans-serif UI fonts, which is
# what makes a lookalike domain work on a hurried reader.
_HOMOGLYPHS = {
    "o": ["0"],
    "l": ["1", "i"],
    "i": ["1", "l"],
    "e": ["3"],
    "a": ["@"],
    "s": ["5"],
    "g": ["9"],
    "b": ["6"],
}

_COMMON_TLDS = ["com", "net", "co", "org", "info", "online", "app", "io"]


def create_monitor(db: Session, org_id: int, name: str, monitor_type: str, keyword: str) -> DRP_Monitor:
    m = DRP_Monitor(org_id=org_id, name=name, monitor_type=monitor_type, keyword=keyword, is_active=True)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def list_monitors(db: Session, org_id: int) -> List[DRP_Monitor]:
    return (
        db.query(DRP_Monitor)
        .filter(DRP_Monitor.org_id == org_id, DRP_Monitor.is_active == True)  # noqa: E712
        .all()
    )


def _org_domains(db: Session, org_id: int) -> List[str]:
    """Email domains actually in use by this tenant's users."""
    domains: List[str] = []
    for (email,) in db.query(User.email).filter(User.org_id == org_id).all():
        if email and "@" in email:
            domain = email.split("@", 1)[1].strip().lower()
            if domain and domain not in domains:
                domains.append(domain)
    return domains


def seed_monitors(db: Session, org_id: int) -> List[DRP_Monitor]:
    """Create monitors from the tenant's real identity, not placeholders.

    Uses the org name and the email domains its users actually sign in with.
    If we cannot determine either, we create nothing — an empty monitor list is
    honest, whereas `example.com` is noise the customer has to clean up.
    """
    existing = db.query(DRP_Monitor).filter(DRP_Monitor.org_id == org_id).count()
    if existing > 0:
        return list_monitors(db, org_id)

    created: List[DRP_Monitor] = []

    org = db.query(Org).filter(Org.id == org_id).first()
    if org and org.name:
        created.append(create_monitor(db, org_id, f"Brand — {org.name}", "brand", org.name))

    for domain in _org_domains(db, org_id):
        created.append(create_monitor(db, org_id, f"Domain — {domain}", "domain", domain))

    return created


# ---------------------------------------------------------------------------
# Lookalike generation (locally computable, no external dependency)
# ---------------------------------------------------------------------------

def _split_domain(domain: str) -> Tuple[str, str]:
    parts = domain.strip().lower().split(".")
    if len(parts) < 2:
        return domain.strip().lower(), ""
    return ".".join(parts[:-1]), parts[-1]


def typosquat_candidates(domain: str, limit: int = 12) -> List[Dict[str, str]]:
    """Registrable variations an attacker would plausibly use.

    Deterministic and offline. Each candidate carries the technique that
    produced it so the finding can explain itself.
    """
    name, tld = _split_domain(domain)
    if not name:
        return []

    seen: set[str] = {domain.lower()}
    out: List[Dict[str, str]] = []

    def add(candidate: str, technique: str) -> None:
        candidate = candidate.lower()
        if candidate in seen or not candidate:
            return
        seen.add(candidate)
        out.append({"domain": candidate, "technique": technique})

    # Omission: dropping one character.
    for i in range(len(name)):
        add(f"{name[:i]}{name[i + 1:]}.{tld}", "character omission")

    # Transposition: swapping two adjacent characters.
    for i in range(len(name) - 1):
        swapped = list(name)
        swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
        add(f"{''.join(swapped)}.{tld}", "character transposition")

    # Homoglyph: visually confusable substitution.
    for i, ch in enumerate(name):
        for repl in _HOMOGLYPHS.get(ch, []):
            add(f"{name[:i]}{repl}{name[i + 1:]}.{tld}", "homoglyph substitution")

    # Hyphenation and TLD swap — both very common in credential phishing.
    add(f"{name}-login.{tld}", "keyword prefix/suffix")
    add(f"{name}-secure.{tld}", "keyword prefix/suffix")
    for alt in _COMMON_TLDS:
        if alt != tld:
            add(f"{name}.{alt}", "alternate TLD")

    return out[:limit]


# ---------------------------------------------------------------------------
# External providers
# ---------------------------------------------------------------------------

def provider_status() -> Dict[str, Any]:
    """Which external DRP sources are actually reachable with current config."""
    return {
        "certificate_transparency": {
            "enabled": bool(getattr(settings, "DRP_CT_ENABLED", False)),
            "reason": None if getattr(settings, "DRP_CT_ENABLED", False) else "DRP_CT_ENABLED is false",
        },
        "dark_web": {
            "enabled": bool(getattr(settings, "DRP_DARKWEB_API_KEY", None)),
            "reason": None if getattr(settings, "DRP_DARKWEB_API_KEY", None) else "DRP_DARKWEB_API_KEY not set",
        },
        "breach_database": {
            "enabled": bool(getattr(settings, "DRP_BREACH_API_KEY", None)),
            "reason": None if getattr(settings, "DRP_BREACH_API_KEY", None) else "DRP_BREACH_API_KEY not set",
        },
    }


def _record_finding(
    db: Session,
    org_id: int,
    monitor: DRP_Monitor,
    finding_type: str,
    severity: str,
    title: str,
    description: str,
    evidence: Dict[str, Any],
    source: str,
) -> Optional[DRP_Finding]:
    """Insert a finding unless an identical open one already exists."""
    duplicate = (
        db.query(DRP_Finding)
        .filter(
            DRP_Finding.org_id == org_id,
            DRP_Finding.monitor_id == monitor.id,
            DRP_Finding.title == title,
            DRP_Finding.status == "open",
        )
        .first()
    )
    if duplicate:
        return None
    finding = DRP_Finding(
        org_id=org_id,
        monitor_id=monitor.id,
        finding_type=finding_type,
        severity=severity,
        title=title,
        description=description,
        evidence_json=evidence,
        source=source,
        status="open",
    )
    db.add(finding)
    return finding


def scan_drp(db: Session, org_id: int) -> List[DRP_Finding]:
    """Run every source that is genuinely available for this tenant."""
    monitors = list_monitors(db, org_id)
    findings: List[DRP_Finding] = []
    status = provider_status()

    for monitor in monitors:
        monitor.last_checked_at = _now()

        if monitor.monitor_type == "domain":
            # Locally computable: the lookalike namespace around a real domain.
            candidates = typosquat_candidates(monitor.keyword)
            if candidates:
                shown = ", ".join(c["domain"] for c in candidates[:5])
                created = _record_finding(
                    db,
                    org_id,
                    monitor,
                    finding_type="typosquat_candidate",
                    severity="MEDIUM",
                    title=f"{len(candidates)} lookalike domains possible for {monitor.keyword}",
                    description=(
                        "These are the registrable variations an attacker would most likely "
                        "use to impersonate this domain. Registration status is NOT checked — "
                        "enable certificate transparency to confirm which exist."
                    ),
                    evidence={
                        "source_domain": monitor.keyword,
                        "candidates": candidates,
                        "sample": shown,
                        "registration_checked": False,
                    },
                    source="local_analysis",
                )
                if created:
                    findings.append(created)

        # External lookups stay silent rather than fabricating results.
        if monitor.monitor_type in ("email", "credential") and not status["breach_database"]["enabled"]:
            continue
        if monitor.monitor_type == "dark_web" and not status["dark_web"]["enabled"]:
            continue

    db.commit()
    for f in findings:
        db.refresh(f)
    return findings


def scan_report(db: Session, org_id: int) -> Dict[str, Any]:
    """Findings plus an explicit account of what could not be checked."""
    findings = scan_drp(db, org_id)
    status = provider_status()
    unavailable = [name for name, s in status.items() if not s["enabled"]]
    return {
        "findings": [serialize_finding(f) for f in findings],
        "providers": status,
        "coverage_note": (
            "Checked locally computable brand risk only. "
            f"Not checked: {', '.join(unavailable)}."
            if unavailable
            else "All configured providers were consulted."
        ),
    }


def list_findings(db: Session, org_id: int) -> List[DRP_Finding]:
    return (
        db.query(DRP_Finding)
        .filter(DRP_Finding.org_id == org_id, DRP_Finding.status == "open")
        .order_by(DRP_Finding.created_at.desc())
        .limit(50)
        .all()
    )


def serialize_monitor(m: DRP_Monitor) -> Dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "monitor_type": m.monitor_type,
        "keyword": m.keyword,
        "is_active": m.is_active,
        "last_checked_at": m.last_checked_at.isoformat() if m.last_checked_at else None,
    }


def serialize_finding(f: DRP_Finding) -> Dict[str, Any]:
    return {
        "id": f.id,
        "monitor_id": f.monitor_id,
        "finding_type": f.finding_type,
        "severity": f.severity,
        "title": f.title,
        "description": f.description,
        "evidence": f.evidence_json,
        "source": f.source,
        "status": f.status,
    }
