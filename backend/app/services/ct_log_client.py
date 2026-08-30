"""Certificate Transparency lookups via crt.sh.

This is the piece that turns a lookalike *candidate* into a finding worth
acting on. Generating "acme-login.com is the shape an attacker would use" is
cheap and mostly noise; proving that someone actually obtained a TLS
certificate for it is a real, dated, attributable event.

Every publicly-trusted CA must log issuance to public CT logs, so a
certificate appearing for a domain you do not own is strong evidence that
infrastructure is being stood up — usually days before it is used.

Three properties matter more than coverage here:

* **A failed lookup is never a clean result.** Network errors, rate limits and
  timeouts return ``ok=False`` with a reason. Callers must not report
  "no lookalikes registered" when the truth is "we could not check".
* **No key, no silent default.** crt.sh needs no credential, but the outbound
  call is opt-in via ``DRP_CT_ENABLED`` because some deployments forbid egress.
* **Only positive confirmations become findings.** Absence of a certificate is
  not evidence of absence of a domain — plenty of malicious domains never get
  a cert, and CT only covers publicly-trusted issuance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from app.core.config import settings

_LOGGER = logging.getLogger(__name__)

# crt.sh is a shared free service. Keep the footprint small and identifiable.
_USER_AGENT = "NOCTRA-DRP/1.0 (+certificate-transparency-monitoring)"


@dataclass
class CTResult:
    """Outcome of a single CT lookup.

    ``ok`` distinguishes "checked, found nothing" from "could not check",
    which the caller must not conflate.
    """

    domain: str
    ok: bool
    registered: bool = False
    reason: Optional[str] = None
    certificates: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def first_seen(self) -> Optional[str]:
        stamps = [c["not_before"] for c in self.certificates if c.get("not_before")]
        return min(stamps) if stamps else None

    @property
    def issuers(self) -> List[str]:
        seen: List[str] = []
        for cert in self.certificates:
            issuer = cert.get("issuer")
            if issuer and issuer not in seen:
                seen.append(issuer)
        return seen


def is_enabled() -> bool:
    return bool(getattr(settings, "DRP_CT_ENABLED", False))


def _shorten_issuer(issuer_name: str) -> str:
    """'C=US, O=Let's Encrypt, CN=R3' -> "Let's Encrypt"."""
    for part in (issuer_name or "").split(","):
        part = part.strip()
        if part.startswith("O="):
            return part[2:].strip()
    return (issuer_name or "unknown").strip()[:120]


def _parse_entries(payload: Any, domain: str) -> List[Dict[str, Any]]:
    """Normalise crt.sh rows, keeping only certs that really cover `domain`.

    crt.sh matches loosely, and ``name_value`` is a newline-separated SAN list,
    so we re-check the match ourselves rather than trusting the query.
    """
    if not isinstance(payload, list):
        return []

    target = domain.lower().lstrip("*.")
    out: List[Dict[str, Any]] = []
    seen_serials: set[str] = set()

    for row in payload:
        if not isinstance(row, dict):
            continue

        names = {
            n.strip().lower().lstrip("*.")
            for n in str(row.get("name_value", "")).split("\n")
            if n.strip()
        }
        common = str(row.get("common_name", "")).strip().lower().lstrip("*.")
        if common:
            names.add(common)
        if target not in names:
            continue

        # Precertificate and final certificate share a serial; count once.
        serial = str(row.get("serial_number") or row.get("id") or "")
        if serial and serial in seen_serials:
            continue
        if serial:
            seen_serials.add(serial)

        out.append(
            {
                "id": row.get("id"),
                "issuer": _shorten_issuer(str(row.get("issuer_name", ""))),
                "not_before": str(row.get("not_before") or "") or None,
                "not_after": str(row.get("not_after") or "") or None,
                "names": sorted(names)[:10],
            }
        )

    out.sort(key=lambda c: c.get("not_before") or "")
    return out


def lookup_domain(domain: str, timeout: Optional[float] = None) -> CTResult:
    """Ask crt.sh whether any CT-logged certificate exists for `domain`."""
    domain = (domain or "").strip().lower()
    if not domain:
        return CTResult(domain=domain, ok=False, reason="empty domain")

    if not is_enabled():
        return CTResult(domain=domain, ok=False, reason="DRP_CT_ENABLED is false")

    url = getattr(settings, "DRP_CT_URL", "https://crt.sh/")
    timeout = timeout if timeout is not None else getattr(settings, "DRP_CT_TIMEOUT", 15.0)

    try:
        resp = requests.get(
            url,
            params={"q": domain, "output": "json"},
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            timeout=timeout,
        )
    except requests.Timeout:
        return CTResult(domain=domain, ok=False, reason=f"crt.sh timed out after {timeout:g}s")
    except Exception as exc:  # network unreachable, DNS failure, TLS error
        _LOGGER.debug("CT lookup failed for %s: %s", domain, exc)
        return CTResult(domain=domain, ok=False, reason=f"crt.sh unreachable: {str(exc)[:120]}")

    if resp.status_code == 429:
        return CTResult(domain=domain, ok=False, reason="crt.sh rate limited this client (HTTP 429)")
    if resp.status_code != 200:
        return CTResult(domain=domain, ok=False, reason=f"crt.sh returned HTTP {resp.status_code}")

    # An empty body is crt.sh's way of saying "no records", not an error.
    body = (resp.text or "").strip()
    if not body:
        return CTResult(domain=domain, ok=True, registered=False)

    try:
        payload = resp.json()
    except Exception:
        return CTResult(domain=domain, ok=False, reason="crt.sh returned a non-JSON response")

    certificates = _parse_entries(payload, domain)
    return CTResult(
        domain=domain,
        ok=True,
        registered=bool(certificates),
        certificates=certificates,
    )


def lookup_many(domains: List[str], limit: int = 12) -> List[CTResult]:
    """Look up several candidates, stopping early if the service is unusable.

    A rate limit or an unreachable host applies to the whole run, so we abort
    rather than hammer a free service and collect identical failures.
    """
    results: List[CTResult] = []
    for domain in domains[:limit]:
        result = lookup_domain(domain)
        results.append(result)
        if not result.ok and result.reason and (
            "rate limited" in result.reason or "unreachable" in result.reason
        ):
            break
    return results
