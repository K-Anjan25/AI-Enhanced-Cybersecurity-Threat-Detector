import string
import uuid


from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class Company(Base):
    __tablename__ = "companies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    api_key = Column(String(255), unique=True, nullable=False)
    plan = Column(String(50), default="beta")  # free, pro, enterprise
    created_at = Column(DateTime, default=datetime.utcnow)
    
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    company = relationship("Company", backref="users")
    email = Column(String, unique=True, nullable=True)
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
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    company = relationship("Company", backref="alerts")
    created_at = Column(DateTime, default=datetime.utcnow)
