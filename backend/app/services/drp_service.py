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
from app.services import ct_log_client

def _now():
    return datetime.now(timezone.utc)


# Characters that render near-identically in most sans-serif UI fonts, which is
# what makes a lookalike domain work on a hurried reader.
#
# Only substitutions that produce a *registrable* domain belong here: the
# hostname grammar allows a-z, 0-9 and hyphen, so "@" for "a" is a font trick
# that cannot be bought and would only waste a lookup.
_HOMOGLYPHS = {
    "o": ["0"],
    "l": ["1", "i"],
    "i": ["1", "l"],
    "e": ["3"],
    "a": ["4"],
    "s": ["5"],
    "g": ["9"],
    "b": ["6"],
    "z": ["2"],
}

# Multi-character confusables. "rn" for "m" is the classic — it is the single
# most effective lookalike in practice, because at UI font sizes "rn" and "m"
# are nearly indistinguishable (acrne.com vs acme.com).
_MULTI_HOMOGLYPHS = [
    ("m", "rn"),
    ("m", "nn"),
    ("w", "vv"),
    ("d", "cl"),
    ("cl", "d"),
    ("rn", "m"),
    ("vv", "w"),
]

# A label may contain only these characters, and may not start or end with "-".
_DOMAIN_LABEL_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")


def _is_registrable(candidate: str) -> bool:
    """Reject anything the DNS would not accept, before we spend a lookup."""
    if "." not in candidate:
        return False
    labels = candidate.split(".")
    if any(not label for label in labels):
        return False
    for label in labels:
        if len(label) > 63 or not set(label) <= _DOMAIN_LABEL_CHARS:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
    return len(candidate) <= 253

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
        if candidate in seen or not candidate or not _is_registrable(candidate):
            return
        seen.add(candidate)
        out.append({"domain": candidate, "technique": technique})

    # Multi-character confusables first: "rn" for "m" is the highest-yield
    # lookalike in the wild, so it should survive the result limit.
    for src, repl in _MULTI_HOMOGLYPHS:
        start = 0
        while True:
            i = name.find(src, start)
            if i == -1:
                break
            add(f"{name[:i]}{repl}{name[i + len(src):]}.{tld}", f"'{src}' rendered as '{repl}'")
            start = i + 1

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
            "enabled": ct_log_client.is_enabled(),
            "reason": None if ct_log_client.is_enabled() else "DRP_CT_ENABLED is false",
        },
        # No client has been written for either of these yet. Reporting
        # "enabled" from the mere presence of an API key would be a false
        # clean: the scan loop has nothing to call, so every monitor would be
        # stamped as checked while nothing was looked up. They stay disabled
        # until a real lookup exists, whatever the configuration says.
        "dark_web": {
            "enabled": False,
            "reason": (
                "no dark-web lookup is implemented; DRP_DARKWEB_API_KEY alone "
                "does not enable one"
            ),
        },
        "breach_database": {
            "enabled": False,
            "reason": (
                "no breach-database lookup is implemented; DRP_BREACH_API_KEY "
                "alone does not enable one"
            ),
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


def _scan_domain_monitor(
    db: Session,
    org_id: int,
    monitor: DRP_Monitor,
    status: Dict[str, Any],
) -> List[DRP_Finding]:
    """Lookalike analysis for one domain, escalated by CT where available.

    Without CT we can only say "these are the shapes an attacker would use".
    With CT we can say "someone obtained a certificate for this one, on this
    date, from this CA" — which is an actual event, and is raised to HIGH.
    """
    findings: List[DRP_Finding] = []
    candidates = typosquat_candidates(monitor.keyword)
    if not candidates:
        return findings

    ct_available = status["certificate_transparency"]["enabled"]
    confirmed: List[Dict[str, Any]] = []
    ct_failure: Optional[str] = None

    if ct_available:
        results = ct_log_client.lookup_many([c["domain"] for c in candidates])
        technique_of = {c["domain"]: c["technique"] for c in candidates}
        checked = 0

        for result in results:
            if not result.ok:
                # First real failure describes the whole run; do not claim
                # the remaining candidates were checked and found clean.
                ct_failure = ct_failure or result.reason
                continue
            checked += 1
            if not result.registered:
                continue

            confirmed.append({"domain": result.domain, "first_seen": result.first_seen})
            created = _record_finding(
                db,
                org_id,
                monitor,
                finding_type="lookalike_domain_registered",
                severity="HIGH",
                title=f"Lookalike domain {result.domain} has a live TLS certificate",
                description=(
                    f"A certificate for {result.domain} appears in public Certificate "
                    f"Transparency logs, so this lookalike of {monitor.keyword} is not "
                    "hypothetical — someone has stood up infrastructure for it. Typical "
                    "next step is a phishing campaign against your staff or customers. "
                    "Verify whether your organisation owns it; if not, consider takedown "
                    "and pre-emptively block the domain at your mail and web gateways."
                ),
                evidence={
                    "source_domain": monitor.keyword,
                    "lookalike_domain": result.domain,
                    "technique": technique_of.get(result.domain),
                    "first_seen": result.first_seen,
                    "issuers": result.issuers,
                    "certificate_count": len(result.certificates),
                    "certificates": result.certificates[:5],
                    "registration_checked": True,
                    "crtsh_url": f"https://crt.sh/?q={result.domain}",
                },
                source="certificate_transparency",
            )
            if created:
                findings.append(created)

    # The candidate-list finding stays useful, but its wording and severity
    # depend on whether we were actually able to verify anything.
    if ct_available and not ct_failure:
        description = (
            f"Checked all {len(candidates)} plausible lookalikes of {monitor.keyword} "
            "against public Certificate Transparency logs. "
            + (
                f"{len(confirmed)} had certificates and are reported separately."
                if confirmed
                else "None currently have a logged certificate. Note that CT only covers "
                "publicly-trusted certificates, so a domain can be registered and hostile "
                "without appearing here."
            )
        )
        severity = "LOW" if not confirmed else "MEDIUM"
    elif ct_available and ct_failure:
        description = (
            f"These are the registrable variations an attacker would most likely use to "
            f"impersonate {monitor.keyword}. Certificate Transparency verification was "
            f"attempted but did not complete ({ct_failure}), so registration status is "
            "unconfirmed — this is not a clean result."
        )
        severity = "MEDIUM"
    else:
        description = (
            "These are the registrable variations an attacker would most likely use to "
            "impersonate this domain. Registration status is NOT checked — set "
            "DRP_CT_ENABLED to confirm which of these actually exist."
        )
        severity = "MEDIUM"

    created = _record_finding(
        db,
        org_id,
        monitor,
        finding_type="typosquat_candidate",
        severity=severity,
        title=f"{len(candidates)} lookalike domains possible for {monitor.keyword}",
        description=description,
        evidence={
            "source_domain": monitor.keyword,
            "candidates": candidates,
            "sample": ", ".join(c["domain"] for c in candidates[:5]),
            "registration_checked": bool(ct_available and not ct_failure),
            "registered_confirmed": confirmed,
            "verification_error": ct_failure,
        },
        source="certificate_transparency" if ct_available and not ct_failure else "local_analysis",
    )
    if created:
        findings.append(created)

    return findings


def scan_drp(db: Session, org_id: int) -> List[DRP_Finding]:
    """Run every source that is genuinely available for this tenant."""
    monitors = list_monitors(db, org_id)
    findings: List[DRP_Finding] = []
    status = provider_status()

    for monitor in monitors:
        if monitor.monitor_type == "domain":
            # Only the domain monitor has a real implementation behind it.
            monitor.last_checked_at = _now()
            findings.extend(_scan_domain_monitor(db, org_id, monitor, status))
            continue

        # Everything else depends on a provider that does not exist yet.
        # Leaving last_checked_at untouched is deliberate: stamping it would
        # tell the operator this monitor was examined and found clean.
        if monitor.monitor_type in ("email", "credential"):
            if not status["breach_database"]["enabled"]:
                continue
        elif monitor.monitor_type == "dark_web":
            if not status["dark_web"]["enabled"]:
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
    available = [name for name, s in status.items() if s["enabled"]]

    if not unavailable:
        note = "All configured providers were consulted."
    elif available:
        note = (
            f"Checked: {', '.join(available)}, plus locally computable brand risk. "
            f"Not checked: {', '.join(unavailable)}."
        )
    else:
        note = (
            "Checked locally computable brand risk only. "
            f"Not checked: {', '.join(unavailable)}."
        )

    return {
        "findings": [serialize_finding(f) for f in findings],
        "providers": status,
        "coverage_note": note,
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
