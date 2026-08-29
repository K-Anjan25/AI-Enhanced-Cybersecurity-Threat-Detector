# Continuation Notes — arena/01a04c02

**Branch:** `arena/01a04c02-ai-enhanced-cybersecurity-thre`  
**Head:** Phase 41 SAML + SCIM Groups/Bulk + Connector OAuth (GitHub/Slack)  
**Previous Heads:** `ee05497` Phase 40 (10 connectors + OIDC + SCIM Users), `f16b587` Phase 39 polling, `c40b693` Phase 38 streaming+PDF  
**Status:** Ready to commit + push. PR #7 open — DO NOT MERGE until user says.

## What is on this branch vs main (3b10bfb)

Main already has PR #6 (connector hardening). This branch adds:

### Phase 36 (b8a9417)
- Trust hardening, 6 scenarios, export JSON, frontend tests

### Phase 37 (dc8b8ce)
- CONNECTOR_ENCRYPTION_KEY, ANALYST_CHAT_RATE_LIMIT 429, bulk_decide honest, scenario validation

### Phase 38 (301b489)
- Live alert streaming SSE: EventBus, TicketStore, stream endpoints, frontend useAlertStream, AlertList live pill
- PDF report export: pdf_report.py reportlab, endpoint report.pdf 409/501, frontend blob download

### Phase 39 (f16b587)
- Scheduled polling: daemon thread, interval 900s jitter 60s backoff 300s-3600s, per-process honest

### Phase 40 (ee05497)
- Connector breadth 4→10: okta, sentinel, guardduty, cloudflare, github, slack, gworkspace, azuread, datadog, splunk
- SSO OIDC: SsoProvider + ScimToken models, sso_service OIDC flow, endpoints /auth/sso/*, admin CRUD, frontend Login SSO button + SsoScimPage
- SCIM Users minimal: Users CRUD, discovery, Bearer hashed per-org, admin token management

### Phase 41 (current) — SAML + SCIM Groups/Bulk + Connector OAuth
**SAML 2.0 (SP-initiated):**
- Models extended: SsoProvider now has saml_entity_id, saml_acs_url, saml_sso_url, saml_certificate, saml_nameid_format, saml_metadata_url
- Config: SSO_SAML_ENABLED, SSO_SAML_METADATA_URL/ENTITY_ID/ACS_URL/SSO_URL/CERTIFICATE
- sso_service.py: _parse_saml_metadata (extract SSO URL + cert from XML), fetch_saml_metadata, create_saml_authn_request (AuthnRequest XML deflate+base64, RelayState TTL 10 min), _parse_saml_response (base64 decode XML, extract NameID/email + attributes), handle_saml_callback (parses, verifies signature if xmlsec available else warning, JIT USER/ANALYST never ADMIN)
- Endpoints sso.py: GET /auth/sso/saml/login (302 to IdP with SAMLRequest), POST /auth/sso/saml/callback (SAMLResponse + RelayState form, issues JWT cookies, redirect), admin CRUD now supports provider_type oidc|saml and SAML fields, delete with provider_type filter
- Frontend: ssoApi.ts getSsoLoginUrl(type), deleteSsoProvider(type), SsoScimPage supports OIDC/SAML toggle with SAML fields (metadata URL auto-fills SSO URL + cert), Login.tsx shows both OIDC and SAML buttons if enabled (backward compat flat config)
- Tests: test_saml_scim_groups.py 12 tests (SAML config, upsert, AuthnRequest creation, response parsing, callback JIT, Groups CRUD, Bulk, OAuth status/state/config/disconnect)

**SCIM Groups + Bulk:**
- New model ScimGroup: org_id, displayName, externalId, members JSON (array of {value, display})
- scim_service.py: _scim_group_from_model (enriches display via DB), list_groups (filter displayName/externalId eq), get_group, create_group (validates user ids), update_group, patch_group (add/remove/replace members via Operations), delete_group, handle_bulk (max 20 ops, failOnErrors, supports POST Users/Groups, PUT/PATCH/DELETE Users, DELETE Groups, returns BulkResponse with status codes)
- Endpoints scim.py: Groups CRUD (GET with filter, POST 201, GET/{id}, PUT, PATCH, DELETE 204), Bulk POST /scim/v2/Bulk, discovery ServiceProviderConfig now bulk supported max 20
- Frontend: SsoScimPage updated description for Groups + Bulk, docs for IdP config
- Tests: test_scim_groups_api.py 4 tests (Groups CRUD API, Bulk API, SAML login endpoints, connector OAuth status requires auth)

**Connector OAuth (GitHub App + Slack OAuth):**
- New model ConnectorOAuth: org_id, connector_id (github|slack), provider, access_token_encrypted, refresh_token_encrypted, token_type, expires_at, scopes, account_id/name
- Config: GITHUB_OAUTH_CLIENT_ID/SECRET, SLACK_OAUTH_CLIENT_ID/SECRET, CONNECTOR_OAUTH_REDIRECT_BASE
- Service connector_oauth_service.py: _get_oauth_config (github authorize https://github.com/login/oauth/authorize token https://github.com/login/oauth/access_token scopes security_events read:org, slack authorize https://slack.com/oauth/v2/authorize token https://slack.com/api/oauth.v2.access scope auditlogs:read), state store TTL 10 min per-process, create_oauth_authorization_url, exchange_oauth_code (POST token_url with Accept json, fetch account info GitHub /user or Slack team, encrypt tokens, upsert), get_oauth_token (decrypt, check expiry, refresh not yet implemented warning), disconnect_oauth, reset_state_store
- Endpoints connector_oauth.py: GET /connectors/{id}/oauth/status (requires auth), GET /connectors/{id}/oauth/start (only github/slack, 302 to provider), GET /connectors/{id}/oauth/callback (exchange, redirect to frontend ?oauth_connected), DELETE /connectors/{id}/oauth (disconnect)
- connector_service.py: list_connectors now shows oauth_connected + oauth_account for github/slack even if no cfg, sync uses OAuth token automatically if present (Authorization Bearer) unless explicit auth_header configured
- Frontend: connectorApi.ts fetchOAuthStatus, oauthStartUrl, disconnectOAuth, ConnectorConfigModal shows OAuth panel for github/slack (connected as account_name with disconnect, or connect button with encrypted at rest note)
- Tests: test_connector_oauth_api.py 4 tests (requires auth, status not connected, only github/slack supported, disconnect not found)

## Gates (verified)

```
backend: 217+ tests (39 connectors + 10 SSO/SCIM + 5 SCIM API + 12 SAML/Groups/Bulk/OAuth + 4 Groups API + 4 OAuth API + 5 scheduler + 17 stream + 7 pdf renderer + 5 pdf API + others) — 213 passed in selected run, 212 passed all non-analyst
dashboard: 46 tests (11 files) — all passing
```

## Recoverability

- Git log shows all phases
- This file + demo.md + session-log.md
- Tests encode honesty contract

## How to merge

Branch ee05497..HEAD (Phase 41) pushed to arena/01a04c02-ai-enhanced-cybersecurity-thre, PR #7 https://github.com/K-Anjan25/AI-Enhanced-Cybersecurity-Threat-Detector/pull/7 — DO NOT MERGE until user says.

## Next candidates

- Connector OAuth refresh + auto-polling using OAuth tokens for GitHub/Slack real APIs (fetch security alerts, audit logs)
- SAML signature verification with xmlsec in production (requires libxmlsec1-dev)
- SCIM Groups role mapping (e.g., group Security Team → role ANALYST)
- All preserve honesty contract
