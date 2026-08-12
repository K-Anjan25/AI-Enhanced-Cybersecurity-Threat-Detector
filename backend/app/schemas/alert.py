from pydantic import BaseModel
from typing import Optional, Dict, Any

class LogAnalyzeRequest(BaseModel):
    log: Dict[str, Any]

class AlertResponse(BaseModel):
    id: int
    alert_type: Optional[str]
    source_ip: Optional[str]
    source: Optional[str]
    severity: Optional[str]
    score: Optional[float]
    message: Optional[str]
    created_at: str

    class Config:
        from_attributes = True