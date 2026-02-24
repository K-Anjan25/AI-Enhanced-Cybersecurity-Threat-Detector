from sqlalchemy import Column, Integer, String, Float, DateTime
from app.database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, default="analyst")  # admin or analyst


class TokenBlocklist(Base):
    __tablename__ = "token_blocklist"

    id = Column(Integer, primary_key=True)
    jti = Column(String, nullable=False)


class SecurityAlert(Base):
    __tablename__ = "security_alerts"

    id = Column(Integer, primary_key=True, index=True)

    alert_type = Column(String)  # "network" or "log"

    source_ip = Column(String, nullable=True)
    source = Column(String, nullable=True)

    severity = Column(String)
    score = Column(Float)
    message = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)
