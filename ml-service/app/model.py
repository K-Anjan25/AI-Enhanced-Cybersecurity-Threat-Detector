from pydantic import BaseModel
from typing import Optional


class NetworkInput(BaseModel):
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    bytes: float
    duration: float


class LogInput(BaseModel):
    timestamp: str
    level: str
    message: str
    source: Optional[str] = "system"
