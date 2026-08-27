from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict
# Severity taxonomy shared with severity_to_score (LOW/MEDIUM/HIGH/CRITICAL).
Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class DetectionRuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    severity: Severity = "MEDIUM"
    pattern: Optional[str] = None
    is_active: bool = True


class DetectionRuleCreate(DetectionRuleBase):
    pass


class DetectionRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[Severity] = None
    pattern: Optional[str] = None
    is_active: Optional[bool] = None


class DetectionRuleOut(DetectionRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


class IpReputationOut(BaseModel):
    id: int
    ip_address: str
    threat_score: float
    is_blocked: bool
    category: Optional[str] = None
    notes: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class EngineSettings(BaseModel):
    detectionSensitivity: str = "MEDIUM"
    maxConcurrentScans: int = 10
    autoQuarantine: bool = False
    kafkaEnabled: bool = False
    logRetentionDays: int = 30


class SettingsResponse(BaseModel):
    message: str
    settings: EngineSettings


class AuditLogOut(BaseModel):
    id: int
    action: str
    actor: Optional[str] = None
    resource: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
