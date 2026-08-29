from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    alerts,
    ingest,
    users,
    public_users,
    admin,
    engine,
    audit,
    analytics,
    rules,
    reputation,
    cases,
    entities,
    soar,
    ml,
    telemetry,
    analyst,
    connectors,
    stream,
)

api_router = APIRouter()

api_router.include_router(auth.router, tags=["Authentication"])
api_router.include_router(users.router, prefix="/user", tags=["Profile"])
api_router.include_router(alerts.router, tags=["Alerts & Analysis"])
api_router.include_router(ingest.router, tags=["Ingestion"])
api_router.include_router(public_users.router, prefix="/users", tags=["User Administration"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(engine.router, tags=["Engine Settings"])
api_router.include_router(audit.router, tags=["Audit Logs"])
api_router.include_router(analytics.router, tags=["Analytics"])
api_router.include_router(rules.router, tags=["Detection Rules"])
api_router.include_router(reputation.router, tags=["IP Reputation"])
api_router.include_router(cases.router, tags=["Incident Management"])
api_router.include_router(entities.router, tags=["Entity Graph"])
api_router.include_router(soar.router, tags=["SOAR"])
api_router.include_router(ml.router, tags=["Machine Learning"])
api_router.include_router(telemetry.router, tags=["Telemetry"])
api_router.include_router(analyst.router, tags=["Analyst"])
api_router.include_router(connectors.router, tags=["Connectors"])
api_router.include_router(stream.router)
