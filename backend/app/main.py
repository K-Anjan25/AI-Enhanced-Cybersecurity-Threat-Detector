from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import sys
import time
import uuid
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, engine
from app.core.migrations import run_additive_migrations, ensure_default_org
from app.models import TokenBlocklist, User, SecurityAlert, DetectionRule, IpReputation, EngineSetting, AuditLog
from app.api.v1.router import api_router

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)


# --- Structured logging -----------------------------------------------------
_LOGGER = logging.getLogger("app")
if not _LOGGER.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "ts=%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    ))
    _LOGGER.addHandler(handler)
_LOGGER.setLevel(settings.LOG_LEVEL or "INFO")


# --- Request-ID + access-log middleware ------------------------------------
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Attach a request id and log one structured line per request."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    _LOGGER.info(
        "method=%s path=%s status=%s duration_ms=%.1f request_id=%s ip=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
        request.client.host if request.client else "-",
    )
    return response


# Middleware must be registered BEFORE routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    try:
        run_additive_migrations(engine)
        Base.metadata.create_all(bind=engine)
        ensure_default_org(engine)
        _LOGGER.info("Database tables verified/created successfully!")
    except Exception as exc:  # pragma: no cover - DB may be offline during tests/dev
        _LOGGER.warning("Could not create database tables: %s", exc)


app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def health_check():
    return {"status": "healthy", "service": settings.PROJECT_NAME, "version": settings.VERSION}


@app.get("/health/live")
def liveness_probe():
    """Liveness probe: the process is up and can answer requests."""
    return {"status": "alive"}


@app.get("/health/ready")
def readiness_probe():
    """Readiness probe: dependencies (database) are reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on DB availability
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": f"database unreachable: {exc}"},
        )
    return {"status": "ready"}
