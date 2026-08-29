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
    sso,
    scim,
    connector_oauth,
    ocsf,
    compliance,
    apikeys,
    threat_intel,
    soar_exec,
    collaboration,
    sigma_rules,
    compliance_packs,
    org_teams,
    ml_feedback,
    attack_navigator,
    data_lifecycle,
    ha_status,
    ztna,
    hunts,
    vulns,
    ai_agent,
    itdr,
    cspm,
    sbom,
    deception,
    forensics,
    tip,
    compliance_continuous,
    exec_risk,
    data_lake,
    ha_eventbus,
    marketplace,
    finetune,
    risk_based,
    purple_team,
    pdf_export,
    attack_coverage,
    agent_collab,
    soc_tv,
    approval_workflows,
    hunt_notebooks,
    exposure,
    ai_redteam,
    federated,
    compliance_autopilot,
    federated_intel,
    quantum_safe,
    attack_path,
    cart,
    data_fabric,
    soc_manager,
    drp,
    cnapp,
    posture_score,
    noctra_os,
)

api_router = APIRouter()

api_router.include_router(auth.router, tags=["Authentication"])
api_router.include_router(sso.router, prefix="/auth", tags=["SSO"])
api_router.include_router(scim.router)
api_router.include_router(scim.admin_router)
api_router.include_router(connector_oauth.router)
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
api_router.include_router(ocsf.router)
api_router.include_router(compliance.router)
api_router.include_router(apikeys.router)
# Phases 49-60
api_router.include_router(threat_intel.router)
api_router.include_router(soar_exec.router)
api_router.include_router(collaboration.router)
api_router.include_router(sigma_rules.router)
api_router.include_router(compliance_packs.router)
api_router.include_router(org_teams.router)
api_router.include_router(ml_feedback.router)
api_router.include_router(attack_navigator.router)
api_router.include_router(data_lifecycle.router)
api_router.include_router(ha_status.router)
# Phases 61-63 + 70 AI Agent
api_router.include_router(ztna.router)
api_router.include_router(hunts.router)
api_router.include_router(vulns.router)
api_router.include_router(ai_agent.router)
# Phases 64-69 + 71-72
api_router.include_router(itdr.router)
api_router.include_router(cspm.router)
api_router.include_router(sbom.router)
api_router.include_router(deception.router)
api_router.include_router(forensics.router)
api_router.include_router(tip.router)
api_router.include_router(compliance_continuous.router)
api_router.include_router(exec_risk.router)
# Phases 73-80
api_router.include_router(data_lake.router)
api_router.include_router(ha_eventbus.router)
api_router.include_router(marketplace.router)
api_router.include_router(finetune.router)
api_router.include_router(risk_based.router)
api_router.include_router(purple_team.router)
api_router.include_router(pdf_export.router)
# Phases 81-84
api_router.include_router(attack_coverage.router)
api_router.include_router(agent_collab.router)
api_router.include_router(soc_tv.router)
# Phases 85-88
api_router.include_router(approval_workflows.router)
api_router.include_router(hunt_notebooks.router)
api_router.include_router(exposure.router)
api_router.include_router(ai_redteam.router)
# Phases 89-90
api_router.include_router(federated.router)
api_router.include_router(compliance_autopilot.router)
# Phases 91-100
api_router.include_router(federated_intel.router)
api_router.include_router(quantum_safe.router)
api_router.include_router(attack_path.router)
api_router.include_router(cart.router)
api_router.include_router(data_fabric.router)
api_router.include_router(soc_manager.router)
api_router.include_router(drp.router)
api_router.include_router(cnapp.router)
api_router.include_router(posture_score.router)
api_router.include_router(noctra_os.router)
