from pydantic import BaseModel, Field
from typing import Optional


class NetworkInput(BaseModel):
    src_ip: str = "0.0.0.0"
    src_port: int = 0
    dst_ip: str = "0.0.0.0"
    dst_port: int = 0
    bytes: float = 0.0
    duration: float = 0.0
    total_fwd_packets: float = 0.0
    total_bwd_packets: float = 0.0
    total_length_bwd_packets: float = 0.0
    fwd_packet_length_mean: float = 0.0
    bwd_packet_length_mean: float = 0.0
    flow_packets_s: float = 0.0
    avg_packet_size: float = 0.0
    init_win_bytes_forward: float = 0.0


class LogInput(BaseModel):
    timestamp: str = ""
    level: str = "INFO"
    message: str = ""
    source: Optional[str] = "system"


class EmailInput(BaseModel):
    sender: str = ""
    subject: str = ""
    body: str = ""
    recipient: str = ""


class DnsInput(BaseModel):
    domain: str
    query_type: str = "A"
    answer_ips: Optional[list[str]] = Field(default_factory=list)


class PredictionResult(BaseModel):
    service: str
    model: str
    anomaly_score: float = Field(ge=0.0, le=1.0)
    is_anomaly: bool
    severity: str = "LOW"
    confidence: float = Field(ge=0.0, le=1.0)
    indicators: list[str] = Field(default_factory=list)
