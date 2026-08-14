from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DetectionRuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    severity: str = "MEDIUM"
    pattern: Optional[str] = None
    is_active: bool = True


class DetectionRuleCreate(DetectionRuleBase):
    pass


class DetectionRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    pattern: Optional[str] = None
    is_active: Optional[bool] = None


class DetectionRuleOut(DetectionRuleBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class IpReputationOut(BaseModel):
    id: int
    ip_address: str
    threat_score: float
    is_blocked: bool
    category: Optional[str] = None
    notes: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True
