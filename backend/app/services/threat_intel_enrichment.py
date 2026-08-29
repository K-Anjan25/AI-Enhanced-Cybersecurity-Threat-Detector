"""Phase 49: Threat intel enrichment — VirusTotal, AbuseIPDB, Shodan, OTX.

- Enriches IPs/domains/hashes on ingest
- Caches results in Redis (if available) or in-memory TTL dict
- Stores enrichment in alert.threat_intel JSON
- Honest: if API keys not set, returns empty enrichment with reason; never fabricates
- Providers:
  - VirusTotal: IP/domain/file report, malicious/suspicious count
  - AbuseIPDB: abuse confidence score, total reports
  - Shodan: open ports, vulns, tags
  - OTX: pulse count, reputation

Design:
- enrich_ip(ip) -> dict with provider results + aggregated risk
- enrich_domain(domain) -> dict
- enrich_hash(hash) -> dict
- enrich_alert(alert) -> updates threat_intel JSON
- Cache key: ti:{provider}:{indicator}, TTL from settings
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Dict, Any, Optional
from collections import defaultdict

import requests

from app.core.config import settings

_LOGGER = logging.getLogger(__name__)

# In-memory cache fallback: key -> (value, expires_at)
_mem_cache: Dict[str, tuple[Dict[str, Any], float]] = {}

# Optional Redis
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = getattr(settings, "REDIS_URL", None)
    if not redis_url:
        return None
    try:
        import redis

        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    redis_client = _get_redis()
    if redis_client:
        try:
            import json

            raw = redis_client.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    # memory fallback
    entry = _mem_cache.get(key)
    if entry:
        val, exp = entry
        if time.time() < exp:
            return val
        else:
            _mem_cache.pop(key, None)
    return None


def _cache_set(key: str, value: Dict[str, Any], ttl: int = 3600):
    redis_client = _get_redis()
    if redis_client:
        try:
            import json

            redis_client.setex(key, ttl, json.dumps(value))
            return
        except Exception:
            pass
    _mem_cache[key] = (value, time.time() + ttl)


def _http_get(url: str, headers: Dict[str, str] = None, params: Dict[str, Any] = None, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    try:
        resp = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
        if resp.status_code == 429:
            _LOGGER.warning("Threat intel rate limited: %s", url)
            return {"error": "rate_limited", "status": 429}
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text[:1000]}
    except Exception as exc:
        _LOGGER.debug("Threat intel fetch failed %s: %s", url, exc)
        return {"error": str(exc)[:200]}


# ---------------------------------------------------------------------------
# Provider fetchers
# ---------------------------------------------------------------------------

def fetch_virustotal_ip(ip: str) -> Dict[str, Any]:
    api_key = getattr(settings, "VT_API_KEY", None)
    if not api_key:
        return {"provider": "virustotal", "enabled": False, "reason": "VT_API_KEY not set"}
    cache_key = f"ti:vt:ip:{ip}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    url = f"https://www.virustotal.com/api/v3/ip_addresses/{ip}"
    headers = {"x-apikey": api_key}
    data = _http_get(url, headers=headers, timeout=getattr(settings, "THREAT_INTEL_TIMEOUT", 5.0))
    if not data or "error" in data:
        result = {"provider": "virustotal", "ip": ip, "error": data.get("error") if data else "no data", "malicious": 0}
    else:
        attrs = data.get("data", {}).get("attributes", {}) if isinstance(data, dict) else {}
        stats = attrs.get("last_analysis_stats", {}) if isinstance(attrs, dict) else {}
        malicious = stats.get("malicious", 0) if isinstance(stats, dict) else 0
        suspicious = stats.get("suspicious", 0) if isinstance(stats, dict) else 0
        result = {
            "provider": "virustotal",
            "ip": ip,
            "malicious": malicious,
            "suspicious": suspicious,
            "reputation": attrs.get("reputation", 0),
            "tags": attrs.get("tags", [])[:10] if isinstance(attrs.get("tags"), list) else [],
            "enabled": True,
        }
    _cache_set(cache_key, result, ttl=getattr(settings, "THREAT_INTEL_CACHE_TTL_SECONDS", 3600))
    return result


def fetch_abuseipdb_ip(ip: str) -> Dict[str, Any]:
    api_key = getattr(settings, "ABUSEIPDB_API_KEY", None)
    if not api_key:
        return {"provider": "abuseipdb", "enabled": False, "reason": "ABUSEIPDB_API_KEY not set"}
    cache_key = f"ti:abuseipdb:ip:{ip}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    url = "https://api.abuseipdb.com/api/v2/check"
    headers = {"Key": api_key, "Accept": "application/json"}
    params = {"ipAddress": ip, "maxAgeInDays": 90}
    data = _http_get(url, headers=headers, params=params, timeout=getattr(settings, "THREAT_INTEL_TIMEOUT", 5.0))
    if not data or "error" in data:
        result = {"provider": "abuseipdb", "ip": ip, "error": data.get("error") if data else "no data", "abuse_confidence": 0}
    else:
        d = data.get("data", {}) if isinstance(data, dict) else {}
        result = {
            "provider": "abuseipdb",
            "ip": ip,
            "abuse_confidence": d.get("abuseConfidenceScore", 0),
            "total_reports": d.get("totalReports", 0),
            "is_whitelisted": d.get("isWhitelisted", False),
            "country": d.get("countryCode"),
            "enabled": True,
        }
    _cache_set(cache_key, result, ttl=getattr(settings, "THREAT_INTEL_CACHE_TTL_SECONDS", 3600))
    return result


def fetch_shodan_ip(ip: str) -> Dict[str, Any]:
    api_key = getattr(settings, "SHODAN_API_KEY", None)
    if not api_key:
        return {"provider": "shodan", "enabled": False, "reason": "SHODAN_API_KEY not set"}
    cache_key = f"ti:shodan:ip:{ip}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    url = f"https://api.shodan.io/shodan/host/{ip}"
    params = {"key": api_key}
    data = _http_get(url, params=params, timeout=getattr(settings, "THREAT_INTEL_TIMEOUT", 5.0))
    if not data or "error" in data:
        result = {"provider": "shodan", "ip": ip, "error": data.get("error") if data else "no data", "ports": []}
    else:
        result = {
            "provider": "shodan",
            "ip": ip,
            "ports": data.get("ports", [])[:20] if isinstance(data.get("ports"), list) else [],
            "vulns": list(data.get("vulns", {}).keys())[:10] if isinstance(data.get("vulns"), dict) else data.get("vulns", [])[:10] if isinstance(data.get("vulns"), list) else [],
            "tags": data.get("tags", [])[:10] if isinstance(data.get("tags"), list) else [],
            "org": data.get("org"),
            "enabled": True,
        }
    _cache_set(cache_key, result, ttl=getattr(settings, "THREAT_INTEL_CACHE_TTL_SECONDS", 3600))
    return result


def fetch_otx_ip(ip: str) -> Dict[str, Any]:
    api_key = getattr(settings, "OTX_API_KEY", None)
    if not api_key:
        return {"provider": "otx", "enabled": False, "reason": "OTX_API_KEY not set"}
    cache_key = f"ti:otx:ip:{ip}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    url = f"https://otx.alienvault.com/api/v1/indicators/IPv4/{ip}/general"
    headers = {"X-OTX-API-KEY": api_key}
    data = _http_get(url, headers=headers, timeout=getattr(settings, "THREAT_INTEL_TIMEOUT", 5.0))
    if not data or "error" in data:
        result = {"provider": "otx", "ip": ip, "error": data.get("error") if data else "no data", "pulse_count": 0}
    else:
        result = {
            "provider": "otx",
            "ip": ip,
            "pulse_count": data.get("pulse_info", {}).get("count", 0) if isinstance(data.get("pulse_info"), dict) else 0,
            "reputation": data.get("reputation", 0),
            "enabled": True,
        }
    _cache_set(cache_key, result, ttl=getattr(settings, "THREAT_INTEL_CACHE_TTL_SECONDS", 3600))
    return result


def enrich_ip(ip: str) -> Dict[str, Any]:
    """Enrich an IP with all available providers, aggregate risk."""
    if not getattr(settings, "THREAT_INTEL_ENABLED", True):
        return {"ip": ip, "enabled": False, "reason": "THREAT_INTEL_ENABLED=False"}

    providers = {}
    # Always try all, even if some disabled — they return enabled=False
    providers["virustotal"] = fetch_virustotal_ip(ip)
    providers["abuseipdb"] = fetch_abuseipdb_ip(ip)
    providers["shodan"] = fetch_shodan_ip(ip)
    providers["otx"] = fetch_otx_ip(ip)

    # Aggregate risk score 0-100
    risk = 0
    reasons = []
    vt = providers.get("virustotal", {})
    if vt.get("malicious", 0) > 0:
        risk += min(vt["malicious"] * 10, 40)
        reasons.append(f"VT malicious {vt['malicious']}")
    abuse = providers.get("abuseipdb", {})
    if abuse.get("abuse_confidence", 0) > 0:
        risk += abuse["abuse_confidence"] * 0.4
        reasons.append(f"AbuseIPDB {abuse['abuse_confidence']}%")
    otx = providers.get("otx", {})
    if otx.get("pulse_count", 0) > 0:
        risk += min(otx["pulse_count"] * 2, 20)
        reasons.append(f"OTX pulses {otx['pulse_count']}")

    risk = min(int(risk), 100)

    band = "unknown"
    if risk >= 80:
        band = "malicious"
    elif risk >= 50:
        band = "suspicious"
    elif risk > 0:
        band = "low"

    return {
        "indicator": ip,
        "type": "ip",
        "risk_score": risk,
        "risk_band": band,
        "reasons": reasons,
        "providers": providers,
        "enriched_at": time.time(),
    }


def enrich_domain(domain: str) -> Dict[str, Any]:
    if not getattr(settings, "THREAT_INTEL_ENABLED", True):
        return {"domain": domain, "enabled": False}
    # For brevity, only VT for domains (AbuseIPDB is IP only)
    api_key = getattr(settings, "VT_API_KEY", None)
    if not api_key:
        return {"domain": domain, "enabled": False, "reason": "VT_API_KEY not set"}
    cache_key = f"ti:vt:domain:{domain}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    url = f"https://www.virustotal.com/api/v3/domains/{domain}"
    headers = {"x-apikey": api_key}
    data = _http_get(url, headers=headers, timeout=getattr(settings, "THREAT_INTEL_TIMEOUT", 5.0))
    if not data or "error" in data:
        result = {"provider": "virustotal", "domain": domain, "error": data.get("error") if data else "no data"}
    else:
        attrs = data.get("data", {}).get("attributes", {}) if isinstance(data, dict) else {}
        stats = attrs.get("last_analysis_stats", {}) if isinstance(attrs, dict) else {}
        result = {
            "provider": "virustotal",
            "domain": domain,
            "malicious": stats.get("malicious", 0) if isinstance(stats, dict) else 0,
            "suspicious": stats.get("suspicious", 0) if isinstance(stats, dict) else 0,
            "enabled": True,
        }
    _cache_set(cache_key, result, ttl=getattr(settings, "THREAT_INTEL_CACHE_TTL_SECONDS", 3600))
    return result


def enrich_hash(file_hash: str) -> Dict[str, Any]:
    if not getattr(settings, "THREAT_INTEL_ENABLED", True):
        return {"hash": file_hash, "enabled": False}
    api_key = getattr(settings, "VT_API_KEY", None)
    if not api_key:
        return {"hash": file_hash, "enabled": False, "reason": "VT_API_KEY not set"}
    cache_key = f"ti:vt:hash:{file_hash}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    url = f"https://www.virustotal.com/api/v3/files/{file_hash}"
    headers = {"x-apikey": api_key}
    data = _http_get(url, headers=headers, timeout=getattr(settings, "THREAT_INTEL_TIMEOUT", 5.0))
    if not data or "error" in data:
        result = {"provider": "virustotal", "hash": file_hash, "error": data.get("error") if data else "no data"}
    else:
        attrs = data.get("data", {}).get("attributes", {}) if isinstance(data, dict) else {}
        stats = attrs.get("last_analysis_stats", {}) if isinstance(attrs, dict) else {}
        result = {
            "provider": "virustotal",
            "hash": file_hash,
            "malicious": stats.get("malicious", 0) if isinstance(stats, dict) else 0,
            "enabled": True,
        }
    _cache_set(cache_key, result, ttl=getattr(settings, "THREAT_INTEL_CACHE_TTL_SECONDS", 3600))
    return result


def enrich_alert_threat_intel(db, alert) -> Dict[str, Any]:
    """Enrich a SecurityAlert row with threat intel, update its threat_intel JSON."""
    if not alert.source_ip:
        return {}
    enrichment = enrich_ip(alert.source_ip)
    # Merge with existing threat_intel if any
    try:
        existing = alert.threat_intel or {}
        if isinstance(existing, str):
            import json

            existing = json.loads(existing)
        merged = {**existing, "enrichment": enrichment}
        alert.threat_intel = merged
        db.commit()
    except Exception:
        db.rollback()
    return enrichment


def get_enrichment_status() -> Dict[str, Any]:
    return {
        "enabled": getattr(settings, "THREAT_INTEL_ENABLED", True),
        "providers": {
            "virustotal": bool(getattr(settings, "VT_API_KEY", None)),
            "abuseipdb": bool(getattr(settings, "ABUSEIPDB_API_KEY", None)),
            "shodan": bool(getattr(settings, "SHODAN_API_KEY", None)),
            "otx": bool(getattr(settings, "OTX_API_KEY", None)),
        },
        "cache_backend": "redis" if _get_redis() else "memory",
        "cache_size": len(_mem_cache),
        "ttl_seconds": getattr(settings, "THREAT_INTEL_CACHE_TTL_SECONDS", 3600),
    }
