"""Phase 63: Vulnerability management + PT."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, ForeignKey, JSON
from datetime import datetime, timezone

from app.core.database import Base


def _now():
    return datetime.now(timezone.utc)


class Vulnerability(Base):
    __tablename__ = "vulnerabilities"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    cve_id = Column(String(30), nullable=True, index=True)  # CVE-2023-12345
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(20), default="MEDIUM")  # CRITICAL, HIGH, MEDIUM, LOW
    cvss_score = Column(Float, nullable=True)
    cvss_vector = Column(String(100), nullable=True)
    affected_asset = Column(String(200), nullable=True)  # ip, hostname, service
    affected_component = Column(String(200), nullable=True)  # package, library
    status = Column(String(20), default="open")  # open, fixed, accepted, false_positive
    discovered_by = Column(String(50), default="scanner")  # scanner, pentest, manual
    # Correlation
    related_alert_id = Column(Integer, ForeignKey("security_alerts.id"), nullable=True)
    related_case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    # Remediation
    remediation = Column(Text, nullable=True)
    # Extra data
    extra = Column(JSON, nullable=True, default=dict)
    first_seen_at = Column(DateTime(timezone=True), default=_now)
    last_seen_at = Column(DateTime(timezone=True), default=_now)
    fixed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)


class VulnScan(Base):
    __tablename__ = "vuln_scans"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    scanner_name = Column(String(100), default="trivy")  # trivy, nessus, qualys, manual
    target = Column(String(300), nullable=False)  # cidr, image, host
    status = Column(String(20), default="completed")  # queued, running, completed, failed
    vuln_count = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    high_count = Column(Integer, default=0)
    scan_results_json = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class PentestFinding(Base):
    __tablename__ = "pentest_findings"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    severity = Column(String(20), default="MEDIUM")
    description = Column(Text, nullable=True)
    proof = Column(Text, nullable=True)  # PoC
    affected_url = Column(String(500), nullable=True)
    status = Column(String(20), default="open")
    tester = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
