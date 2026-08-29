# Continuation Notes — arena/01a04c02

**Branch:** `arena/01a04c02-ai-enhanced-cybersecurity-thre`  
**Head:** Phase 40 connector breadth (10) + SSO OIDC + SCIM 2.0  
**Previous Heads:** `f16b587` Phase 39 polling, `c40b693` Phase 38 docs, `301b489` streaming+PDF, `9afccf0` Phase 37  
**Status:** Ready to commit + push. PR #7 open — DO NOT MERGE until user says.

## What is on this branch vs main (3b10bfb)

Main already has PR #6 (connector hardening). This branch adds:

### Phase 36 (b8a9417)
- Trust hardening, 6 scenarios, export JSON, frontend tests

### Phase 37 (dc8b8ce)
- `CONNECTOR_ENCRYPTION_KEY` dedicated key decouples from JWT rotation
- `ANALYST_CHAT_RATE_LIMIT` 20/min per org:user:case, 429 with Retry-After
- `bulk_decide()` honest pending-only, max 50, endpoint + frontend bulk UI
- Scenario validation 422, chat 429 messaging
- Tests: test_analyst_phase37.py 7 tests

### Phase 38 (301b489)
**Live alert streaming (SSE):**
- `app/core/events.py`: EventBus thread-safe via `call_soon_threadsafe`, per-process scope, queue full → dropped + gap frame, TicketStore single-use 30s TTL
- `app/api/v1/endpoints/stream.py`: POST /stream/ticket, GET /stream/alerts?ticket=, GET /stream/status
- `connector_service.py`: _ingest_events publishes after commit
- Frontend: streamApi.ts, useAlertStream.ts, AlertList live pill
- Tests: 17 stream tests

**PDF report export:**
- `pdf_report.py`: reportlab, pageCompression=0, preserves '(templated fallback)'
- Endpoint `GET /analyst/cases/{id}/report.pdf`: 409 if no report, 501 if missing dep
- Frontend: CasePage Export PDF via blob download
- Tests: 7 renderer + 5 API + 3 frontend PDF

### Phase 39 (f16b587)
**Scheduled polling — watches continuously:**
- `config.py`: CONNECTOR_POLL_ENABLED true, INTERVAL 900s, JITTER 60s, BACKOFF base 300s max 3600s
- `connector_scheduler.py`: daemon thread, _should_poll, backoff exponential, _poll_once, start/stop/reset
- `main.py`: lifespan starts/stops scheduler (per-process honest)
- Tests: 5 scheduler tests

### Phase 40 (current) — connector breadth + SSO/SCIM
**Connector breadth: 4 → 10**
- `connector_service.py` CATALOGUE expanded:
  - okta (Okta Identity Cloud) Identity
  - sentinel (CrowdStrike / Sentinel EDR) Endpoint
  - guardduty (AWS GuardDuty & IAM Audit) Cloud Security
  - cloudflare (Cloudflare Edge WAF) Network & Edge
  - github (GitHub Advanced Security) Code & Supply Chain
  - slack (Slack Enterprise Audit Logs) Collaboration
  - gworkspace (Google Workspace Admin) Productivity
  - azuread (Microsoft Entra ID) Identity
  - datadog (Datadog Cloud SIEM) Observability
  - splunk (Splunk Enterprise Security) SIEM
- More telemetry makes live stream + scheduled poller busy (honest: counts still derived from rows ingested)
- Frontend BriefPage grid already supports wrap, text updated to "10 total, Phase 40"
- Tests: catalogue length assert

**SSO OIDC (enterprise auth):**
- Models: `SsoProvider` (org_id, provider_type oidc, issuer, client_id, client_secret_encrypted, scopes, enabled, jit_provisioning), `ScimToken` (org_id, token_hash, prefix, name, created_by, last_used)
- Config: SSO_ENABLED, SSO_OIDC_ISSUER, CLIENT_ID/SECRET, SCOPES, JIT, DEFAULT_ROLE, SCIM_ENABLED, SCIM_TOKEN fallback
- `sso_service.py`: OIDC discovery via .well-known, state+nonce in-memory TTL 10 min per-process, create_authorization_url, exchange_code, userinfo, decode id_token without verification (logged limitation), handle_callback with JIT provisioning USER/ANALYST never ADMIN, encrypted secrets
- Endpoints `app/api/v1/endpoints/sso.py`: GET /auth/sso/config (public), GET /auth/sso/login (302 to IdP), GET /auth/sso/callback (exchange, issue our JWTs as cookies, redirect to frontend), admin CRUD /admin/sso/providers
- Frontend: `ssoApi.ts`, Login.tsx shows SSO button if enabled, `SsoScimPage.tsx` admin UI for OIDC config + SCIM tokens, route /admin/sso, link in AdminDashboard
- Tests: test_sso_scim.py 10 tests (config, env, upsert, only oidc, state store, token create/verify, list, user CRUD, discovery, catalogue)

**SCIM 2.0 provisioning:**
- `scim_service.py`: hash_token, create/verify token, list tokens, Users CRUD (list with limited filter userName/email/externalId eq, get, create, update, patch active, delete soft-deactivate), discovery ServiceProviderConfig, ResourceTypes, Schemas, Groups minimal empty
- Endpoints `scim.py`: /scim/v2/ServiceProviderConfig, ResourceTypes, Schemas (no auth), /Users (GET, POST), /Users/{id} (GET, PUT, PATCH, DELETE 204), /Groups (minimal), admin /admin/scim/tokens CRUD
- Auth: Bearer token hashed at rest per-org, fallback SCIM_TOKEN env for single-tenant, last_used update
- Honest gaps documented: filtering limited, groups membership not implemented, bulk not implemented, SAML not implemented
- Tests: test_scim_api.py 5 tests (discovery, requires auth, CRUD with token, invalid token, SSO config)
- Frontend: SCIM token management in SsoScimPage (create shows once, list with prefix, delete), docs for IdP config

## Gates (verified)

```
backend: 64+ tests (18 analyst + 7 phase37 + 17 stream + 7 pdf renderer + 5 pdf API + 5 scheduler + 10 SSO/SCIM + 5 SCIM API) — all passing
dashboard: 46 tests (11 files) — all passing (43 previous + 3 SSO/SCIM page)
```

## Recoverability of previous discussion

- Git log shows all phases
- This file + docs/demo.md + docs/session-log.md
- Backend tests encode honesty contract
- PR #7 description

## How to create PR and merge (when you say)

Branch pushed: `f16b587` exists on origin. After Phase 40 commit, push again.

PR #7: https://github.com/K-Anjan25/AI-Enhanced-Cybersecurity-Threat-Detector/pull/7 — DO NOT MERGE until user says.

## Next candidates

- SAML (completes SSO story) — needs xmlsec, metadata parsing
- SCIM Groups membership sync + Bulk
- Connector OAuth (GitHub App, Slack OAuth) instead of shared secret
- All preserve honesty contract
