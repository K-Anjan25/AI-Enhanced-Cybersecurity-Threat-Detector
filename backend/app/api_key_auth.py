from functools import wraps
from flask import request, jsonify
from app.database import SessionLocal
from app.models import Company

def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get("X-API-KEY")

        if not api_key:
            return jsonify({"message": "API key missing"}), 401

        db = SessionLocal()
        company = db.query(Company).filter_by(api_key=api_key).first()

        if not company:
            db.close()
            return jsonify({"message": "Invalid API key"}), 403

        result = fn(company, *args, **kwargs)
        db.close()
        return result

    return wrapper