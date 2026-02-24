from flask import Blueprint, jsonify, request
from app.database import SessionLocal
from app.models import SecurityAlert, User, TokenBlocklist
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt
from app.permissions import role_required
from app.service import process_log

api = Blueprint("api", __name__)
bcrypt = Bcrypt()


@api.route("/register", methods=["POST"])
def register():
    db = SessionLocal()
    data = request.json

    hashed_password = bcrypt.generate_password_hash(
        data["password"]).decode("utf-8")

    user = User(
        username=data["username"],
        password=hashed_password,
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
def analyze():
    log = request.json
    alert = process_log(log, produce_kafka=False)
    return jsonify(alert)


@api.route("/alerts", methods=["GET"])
def get_alerts():
    db = SessionLocal()
    alerts = db.query(SecurityAlert).order_by(
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
    db.query(SecurityAlert).delete()
    db.commit()
    return jsonify({"message": "All alerts cleared"})
