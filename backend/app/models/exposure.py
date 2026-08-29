"""Phase 87: Exposure Management (ASM - Attack Surface Management)."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class ASM_Domain(Base):
    __tablename__ = "asm_domains"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    domain = Column(String(300), nullable=False)
    # Discovery
    discovery_method = Column(String(50), default="manual")  # manual, brute_force, cert_transparency
    is_verified = Column(Boolean, default=False)
    # DNS
    dns_records_json = Column(JSON, default=dict)  # {A: [...], MX: [...]}
    created_at = Column(DateTime(timezone=True), default=_now)

class ASM_AssetExposure(Base):
    __tablename__ = "asm_asset_exposures"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    domain_id = Column(Integer, ForeignKey("asm_domains.id"), nullable=True, index=True)
    asset_type = Column(String(50), default="host")  # host, domain, ip, service, certificate
    name = Column(String(500), nullable=False)  # ip, domain, url
    ip_address = Column(String(50), nullable=True)
    port = Column(Integer, nullable=True)
    service = Column(String(100), nullable=True)  # http, ssh, etc
    # Exposure details
    exposure_type = Column(String(100), default="open_port")  # open_port, expired_cert, exposed_service, misconfig
    severity = Column(String(20), default="MEDIUM")
    description = Column(Text, nullable=True)
    # Evidence
    evidence_json = Column(JSON, default=dict)  # {banner, cert_expiry, headers}
    first_seen_at = Column(DateTime(timezone=True), default=_now)
    last_seen_at = Column(DateTime(timezone=True), default=_now)
    status = Column(String(20), default="open")  # open, fixed, ignored
    created_at = Column(DateTime(timezone=True), default=_now)

class ASM_Certificate(Base):
    __tablename__ = "asm_certificates"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    domain = Column(String(300), nullable=False)
    issuer = Column(String(300), nullable=True)
    subject = Column(String(300), nullable=True)
    not_before = Column(DateTime(timezone=True), nullable=True)
    not_after = Column(DateTime(timezone=True), nullable=True)
    is_expired = Column(Boolean, default=False)
    is_self_signed = Column(Boolean, default=False)
    san_json = Column(JSON, default=list)  # Subject Alternative Names
    created_at = Column(DateTime(timezone=True), default=_now)

class ExposureFinding(Base):
    __tablename__ = "exposure_findings"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    exposure_id = Column(Integer, ForeignKey("asm_asset_exposures.id"), nullable=True)
    title = Column(String(500), nullable=False)
    finding_type = Column(String(100), default="misconfiguration")
    severity = Column(String(20), default="MEDIUM")
    description = Column(Text, nullable=True)
    remediation = Column(Text, nullable=True)
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), default=_now)
