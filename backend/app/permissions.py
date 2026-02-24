from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.database import SessionLocal
from app.models import User


def role_required(required_role):
    def wrapper(fn):
        @wraps(fn)
        @jwt_required()
        def decorator(*args, **kwargs):
            db = SessionLocal()
            username = get_jwt_identity()
            user = db.query(User).filter_by(username=username).first()

            if not user or user.role != required_role:
                return jsonify({"message": "Access forbidden"}), 403

            return fn(*args, **kwargs)

        return decorator
    return wrapper
