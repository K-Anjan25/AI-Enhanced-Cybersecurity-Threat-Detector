from flask import Blueprint, jsonify, request
from app.database import SessionLocal
from app.models import SecurityAlert, User, TokenBlocklist, Company
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt
from app.permissions import role_required
from app.service import process_log
from app.api_key_auth import require_api_key
import secrets
import uuid
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import app

limiter = Limiter(get_remote_address,app=app)

api = Blueprint("api", __name__)
bcrypt = Bcrypt()

@api.route("/api/v1/ingest", methods=["POST"])
@limiter.limit("100 per minute",key_func=lambda: request.headers.get("X-API-Key"))  # Rate limit to prevent abuse
@require_api_key
def ingest(company):
    log = request.json

    alert = process_log(
        log,
        produce_kafka=False,
        company_id=company.id   # <-- NEW
    )

    return jsonify(alert)

@api.route("/register", methods=["POST"])
def register():
    db = SessionLocal()
    data = request.json
    
    company = db.query(Company).first()  # Assuming single company for simplicity

    if not company:
        db.close()
        return jsonify({"message": "Company not found"}), 400

    hashed_password = bcrypt.generate_password_hash(
        data["password"]).decode("utf-8")

    user = User(
        username=data["username"],
        password=hashed_password,
        email=data.get("email"),
        company_id=company.id,
        role=data.get("role", "analyst")
    )

    db.add(user)
    db.commit()
    db.close()

    return jsonify({"message": "User registered successfully"}), 201


@api.route("/login", methods=["POST"])
def login():
    db = SessionLocal()
    data = request.json
    
    user = db.query(User).filter_by(username=data["username"]).first()

    if not user or not bcrypt.check_password_hash(user.password, data["password"]):
        return jsonify({"message": "Invalid credentials"}), 401

    access_token = create_access_token(identity=user.username)
    refresh_token = create_refresh_token(identity=user.username)

    return jsonify(
        access_token=access_token,
        refresh_token=refresh_token,
        role=user.role
    )


@api.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    new_access_token = create_access_token(identity=identity)
    return jsonify(access_token=new_access_token)


@api.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    db = SessionLocal()
    jti = get_jwt()["jti"]

    blocked_token = TokenBlocklist(jti=jti)
    db.add(blocked_token)
    db.commit()
    db.close()

    return jsonify({"message": "Successfully logged out"})


@api.route("/analyze", methods=["POST"])
@jwt_required()
def analyze():
    log = request.json
    username = get_jwt_identity()
    db = SessionLocal()
    user = db.query(User).filter_by(username=username).first()
    alert = process_log(log, produce_kafka=False, company_id=user.company_id)  # <-- NEW
    db.close()
    return jsonify(alert)


@api.route("/alerts", methods=["GET"])
@jwt_required()
def get_alerts():
    db = SessionLocal()
    username = get_jwt_identity()
    user = db.query(User).filter_by(username=username).first()
    alerts = db.query(SecurityAlert).filter_by(company_id=user.company_id).order_by(
        SecurityAlert.created_at.desc()
    ).all()
    db.close()

    return jsonify([{
        "id": a.id,
        "alert_type": a.alert_type,
        "source_ip": a.source_ip,
        "severity": a.severity,
        "score": a.score,
        "message": a.message,
        "created_at": a.created_at.isoformat()
    } for a in alerts])


@api.route("/alerts/clear", methods=["DELETE"])
@role_required("admin")
def clear_alerts():
    db = SessionLocal()
    username = get_jwt_identity()
    user = db.query(User).filter_by(username=username).first()
    db.query(SecurityAlert).filter_by(company_id=user.company_id).delete()
    db.commit()
    db.close()
    return jsonify({"message": "All alerts cleared"})


@api.route("/admin/create-company", methods=["POST"])
@role_required("super_admin")
def create_company():
    db = SessionLocal()
    data = request.json

    api_key = secrets.token_hex(32)
    company_id = str(uuid.uuid4())

    company = Company(
        id=company_id,
        name=data["name"],
        api_key=api_key
    )
    
    hashed_password = bcrypt.generate_password_hash(
        data["admin_password"]).decode("utf-8")
    
    admin_user = User(
        username=data["admin_username"],
        password=hashed_password,
        company_id=company_id,
        role="admin"
    )

    db.add(company)
    db.add(admin_user)
    db.commit()

    response = {
        "company_name": data["name"],
        "api_key": api_key,
        "admin_username": admin_user.username
    }
    
    db.close()
    return jsonify(response), 201
    
