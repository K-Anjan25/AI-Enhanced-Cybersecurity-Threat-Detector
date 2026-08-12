import math
import re

from app.feature_extractor import score_to_severity

# Highly abused TLDs weighted by abuse reports.
SUSPICIOUS_TLDS = {
    ".tk": 0.4, ".ml": 0.4, ".ga": 0.4, ".cf": 0.4, ".gq": 0.4,
    ".xyz": 0.2, ".top": 0.3, ".club": 0.2, ".work": 0.2, ".click": 0.3,
    ".link": 0.3, ".zip": 0.3, ".mov": 0.3, ".buzz": 0.2, ".bid": 0.3,
    ".loan": 0.3, ".win": 0.3, ".men": 0.3, ".stream": 0.3, ".download": 0.3,
}

COMMON_TLDS = {".com", ".org", ".net", ".edu", ".gov", ".mil", ".io", ".co", ".ai", ".dev", ".app"}

# Public DNS servers that should never appear as answer IPs.
KNOWN_DNS_IPS = {
    "8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9",
    "208.67.222.222", "208.67.220.220", "114.114.114.114", "223.5.5.5",
}


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum((c / len(s)) * math.log2(c / len(s)) for c in counts.values())


def predict_domain(dns) -> dict:
    dns = dns if isinstance(dns, dict) else dns.model_dump()
    domain = str(dns.get("domain") or "").strip().lower().rstrip(".")
    answer_ips = dns.get("answer_ips") or []
    query_type = str(dns.get("query_type") or "A").upper()

    indicators = []
    score = 0.0

    if not domain:
        return {
            "anomaly_score": 0.0, "is_anomaly": False, "severity": "LOW",
            "confidence": 0.5, "indicators": ["empty domain"], "model": "dns_rules",
        }

    labels = domain.split(".")
    tld = "." + labels[-1] if len(labels) >= 2 else ""
    sld = labels[-2] if len(labels) >= 2 else ""
    host = labels[0] if len(labels) > 2 else sld

    # 1. Numeric / IP-like domains.
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", domain):
        score += 0.9
        indicators.append("domain is a raw IP address")

    # 2. Suspicious TLD.
    if tld in SUSPICIOUS_TLDS:
        score += SUSPICIOUS_TLDS[tld]
        indicators.append(f"high-abuse TLD {tld}")

    # 3. Long label + high entropy (DGA-style domain generation).
    host_entropy = _entropy(host)
    if len(host) >= 12 and host_entropy >= 3.4:
        score += 0.4
        indicators.append("long high-entropy label (possible DGA)")
    if re.search(r"[aeiou]{3}", host) is None and len(host) >= 8:
        score += 0.1
        indicators.append("label lacks vowel structure (possible DGA)")

    # 4. Punycode / IDN abuse.
    if "xn--" in domain:
        score += 0.5
        indicators.append("punycode homoglyph risk")

    # 5. Hyphen-heavy labels.
    if host.count("-") >= 2:
        score += 0.2
        indicators.append("multiple hyphens in hostname")

    # 6. Digits mixed in label.
    if sum(c.isdigit() for c in host) / len(host) > 0.5 and len(host) > 4:
        score += 0.2
        indicators.append("digit-heavy label")

    # 7. Uncommon query types (TXT used for exfil, ANY discouraged).
    if query_type in ("TXT", "ANY"):
        score += 0.2
        indicators.append(f"uncommon query type {query_type}")

    # 8. Answer IP anomalies.
    for ip in answer_ips:
        if ip in KNOWN_DNS_IPS:
            score -= 0.1
            indicators.append(f"answers to public resolver {ip}")
    if len(answer_ips) > 10:
        score += 0.2
        indicators.append("unusually many answer records")

    score = float(max(0.0, min(1.0, score)))
    is_malicious = score >= 0.6

    return {
        "anomaly_score": round(score, 4),
        "is_anomaly": bool(is_malicious),
        "severity": score_to_severity(score),
        "confidence": round(float(min(0.99, 0.5 + score * 0.4)), 3),
        "indicators": list(dict.fromkeys(indicators)),
        "model": "dns_rules",
    }
