import os
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from app.routes import api
from app.database import Base, engine, SessionLocal
from app.models import TokenBlocklist
from app.kafka_consumer import start_consumer
from app.config import ENABLE_KAFKA
import threading

load_dotenv()

bcrypt = Bcrypt()
jwt = JWTManager()


def create_app():
    app = Flask(__name__)

    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 900  # 15 min
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = 604800  # 7 days
    app.config["JWT_BLACKLIST_ENABLED"] = True
    app.config["JWT_BLACKLIST_TOKEN_CHECKS"] = ["access", "refresh"]

    CORS(app)
    jwt.init_app(app)

    app.register_blueprint(api)

    # ✅ Register blocklist callback INSIDE factory
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        db = SessionLocal()
        token = db.query(TokenBlocklist).filter_by(
            jti=jwt_payload["jti"]
        ).first()
        db.close()
        return token is not None

    return app


Base.metadata.create_all(bind=engine)
app = create_app()

if ENABLE_KAFKA:
    threading.Thread(target=start_consumer, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
