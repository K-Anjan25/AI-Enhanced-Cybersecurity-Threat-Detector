# Requirements Traceability Matrix

Maps every **Functional Requirement (FR)** and **Non-Functional Requirement (NFR)**
to its implementation (module/endpoint), the tests that verify it, and any
design/diagram reference. IDs are defined in
[functional-requirements.md](functional-requirements.md) and
[non-functional-requirements.md](non-functional-requirements.md).

Legend for verification: **UT** = unit/service test, **IT** = integration/API test,
**UI** = dashboard build/UI test, **REV** = code/architecture review.

---

## Functional requirements

| ID | Module / Endpoint | Design ref | Test(s) | Verif |
| --- | --- | --- | --- | --- | --- |
| FR-AUTH-01 | `auth.py /register` | class-diagram, sequence-diagram | `test_endpoints.py`, `test_tenancy.py` | IT |
| FR-AUTH-02 | `auth.py /login` | sequence-diagram | `test_endpoints.py` | IT |
| FR-AUTH-03 | `security.create_access_token/create_refresh_token` | class-diagram | `test_helpers.py` | UT |
| FR-AUTH-04 | `auth.py` cookie set on login/refresh/logout | timing-diagram | `test_endpoints.py` (cookie assertions) | IT |
| FR-AUTH-05 | `auth.py /refresh` | timing-diagram | `test_endpoints.py` | IT |
| FR-AUTH-06 | `token_blocklist` + logout | timing-diagram | `test_endpoints.py` | IT |
| FR-AUTH-07 | `auth.login_limiter` | timing-diagram | `test_endpoints.py` (429) | IT |
| FR-AUTH-08 | `failed_login_attempts` + `is_blocked` | timing-diagram, state-diagram | `test_endpoints.py` (lockout) | IT |
| FR-AUTH-09 | `auth.py` successful login reset | timing-diagram | `test_endpoints.py` | IT |
| FR-AUTH-10 | `forgot-password` env-gated `reset_link` | — | `test_endpoints.py` (prod vs dev) | IT |
| FR-AUTH-11 | `user.py /user/me` | class-diagram | `test_endpoints.py` | IT |
| FR-AUTH-12 | `user_service.update_user_password` | — | `test_endpoints.py` | IT |
| FR-AUTH-13 | `roles` on `User` + `ROLE_PERMISSIONS` | abac.py catalog | `test_endpoints.py` | IT |
| FR-ABAC-01 | `core/abac.py` attribute evaluation | class-diagram | `test_endpoints.py` | IT |
| FR-ABAC-02 | `require_permission`/`require_any_permission` dependencies | component-diagram | `test_endpoints.py` | IT |
| FR-ABAC-03 | `subject_is_active` returns empty set for blocked/inactive | abac.py | `test_endpoints.py` | IT |
| FR-ABAC-04 | `CLEARANCE_REQUIREMENTS` (e.g. `engine:update`=4) | abac.py | `test_endpoints.py` | IT |
| FR-ABAC-05 | `resource_condition_passes` (CRITICAL export/delete) | abac.py | `test_endpoints.py` | IT |
| FR-ABAC-06 | 403 on missing permission | all guarded endpoints | `test_endpoints.py` | IT |
| FR-TENANT-01 | `models/org.py` `Org`, `slug` | class-diagram, ERD | `test_tenancy.py` | UT |
| FR-TENANT-02 | `register` assigns default org | tenancy service | `test_tenancy.py` | UT |
| FR-TENANT-03 | `org_id` FK on tenant tables | database-design ERD | model inspection | REV |
| FR-TENANT-04 | `ensure_default_org` seed + backfill | migrations.py | `test_tenancy.py` | UT |
| FR-TENANT-05 | org-scoped queries in services | case_service, alert_service | `test_cases.py`, `test_tenancy.py` | UT |
| FR-TENANT-06 | admin cross-tenant listing | admin endpoints | — | REV |
| FR-DETECT-01 | `POST /analyze` | activity-diagram | `test_endpoints.py` | IT |
| FR-DETECT-02 | network vs log classifier in `process_log` | alert_service | `test_endpoints.py` | IT |
| FR-DETECT-03 | `ml_client.predict_*` + `score_to_severity` | component-diagram | `test_endpoints.py` | IT |
| FR-DETECT-04 | `_post_with_retry` + heuristic fallback | activity-diagram | `test_ml_client.py` | UT |
| FR-DETECT-05 | `SecurityAlert` persistence | ERD | `test_endpoints.py` | IT |
| FR-DETECT-06 | `mitre.map_alert` on every alert | activity-diagram | `test_mitre.py` | UT |
| FR-DETECT-07 | `threat_intel.enrich_alert` reputation context | component-diagram | `test_threat_intel.py` | UT |
| FR-DETECT-08 | `POST /upload-logs` + `ScanBatch` | state-diagram | `test_endpoints.py` | IT |
| FR-DETECT-09 | background task `pending→processing→completed/failed` | state-diagram | `test_endpoints.py` | IT |
| FR-DETECT-10 | `ScannedAlert` evidence + feed `SecurityAlert` | ERD | `test_endpoints.py` | IT |
| FR-DETECT-11 | `GET /uploads/{id}` | state-diagram | `test_endpoints.py` | IT |
| FR-DETECT-12 | Kafka per-topic publishing toggle | component-diagram | kafka producer tests | UT |
| FR-ALERT-01 | `GET /alerts` pagination | ERD | `test_endpoints.py` | IT |
| FR-ALERT-02 | `get_alert_stats` KPIs | analytics endpoint | `test_endpoints.py` | IT |
| FR-ALERT-03 | CSV export streaming | alerts endpoint | `test_endpoints.py` | IT |
| FR-ALERT-04 | `DELETE /alerts/clear` (alerts:delete) | abac catalog | `test_endpoints.py` | IT |
| FR-ALERT-05 | `POST /cases` with optional `source_alert_id` | class-diagram | `test_cases.py` | UT |
| FR-ALERT-06 | case lifecycle transitions | state-diagram | `test_cases.py` | UT |
| FR-ALERT-07 | `PATCH /cases/{id}` status/priority/assignee | class-diagram | `test_cases.py` | UT |
| FR-ALERT-08 | invalid status/priority → 400 | case_service | `test_cases.py` | UT |
| FR-ALERT-09 | `CASE_CREATED`/`CASE_UPDATED` audit entries | activity-diagram | `test_cases.py` | UT |
| FR-ENGINE-01 | engine settings GET | engine endpoint | `test_endpoints.py` | IT |
| FR-ENGINE-02 | engine settings update (`engine:update`) | abac catalog | `test_endpoints.py` | IT |
| FR-ENGINE-03 | rules CRUD | rules endpoint | `test_endpoints.py` | IT |
| FR-ENGINE-04 | IP reputation CRUD | reputation endpoint | `test_endpoints.py` | IT |
| FR-AUDIT-01 | `create_audit_log` | class-diagram | `test_helpers.py` | UT |
| FR-AUDIT-02 | append-only (ORM rejects UPDATE/DELETE) | database-design | `test_endpoints.py` (append-only) | UT |
| FR-AUDIT-03 | `GET /audit-logs` (audit:read) | abac catalog | `test_endpoints.py` | IT |
| FR-AUDIT-04 | `/health/live` + `/health/ready` | component-diagram | `test_endpoints.py` | IT |
| FR-AUDIT-05 | `X-Request-ID` tracing | middleware | REV |
| FR-STREAM-01 | normalized-event Kafka publishing | component-diagram | kafka producer tests | UT |
| FR-STREAM-02 | `alerts.raised` Kafka publishing | component-diagram | kafka producer tests | UT |
| FR-STREAM-03 | SOAR engine (`actions.executed`, auto + manual trigger) | component-diagram, activity-diagram | `test_soar.py` | UT |
| FR-STREAM-03 (UI) | SOAR automation screens (`/soar`, dry-run + trigger) | activity-diagram | `tsc`+`vite build`; `SoarPage.tsx` | UI |
| FR-STREAM-04 | entity/attack-graph service + graph endpoints | component-diagram | `test_entity_graph.py` | UT/IT |
| FR-STREAM-04 (UI) | entity-graph visualization screens (`/entities`, SVG graph) | component-diagram | `tsc`+`vite build`; `EntitiesPage.tsx` | UI |
| FR-STREAM-05 | ML training-serving pipeline (CronJob retrain + hot-swap) | target-design, ml-pipeline.md | contract tests + `training.py` + `POST /retrain` | UT/REV |
| FR-UI-01..07 | dashboard pages | component-diagram, target-design | `tsc` + `vite build` + UI tests | UI |
| FR-UI-04 | incident/case management screens (`/incidents`) | class-diagram | `tsc`+`vite build`; `IncidentsPage.tsx` | UI |
| FR-UI-07 | MITRE ATT&CK + threat-intel context in alert detail modal | class-diagram | `tsc`+`vite build`; `AlertDetailModal.tsx` | UI |

## Non-functional requirements

| ID | Module / design | Test(s) / verification |
| --- | --- | --- |
| NFR-PERF-01..05 | alert/scan/predict paths | load test (k6/Locust) — baselined; see targets |
| NFR-SEC-01 | `security.py` bcrypt hashing | `test_endpoints.py` password hash check |
| NFR-SEC-02 | JWT exp + JTI blocklist | `test_endpoints.py` refresh/revoke |
| NFR-SEC-03 | httpOnly/SameSite cookies | `test_endpoints.py` cookie assertions |
| NFR-SEC-04 | login limiter + lockout | `test_endpoints.py` |
| NFR-SEC-05 | append-only audit | ORM event tests |
| NFR-SEC-06 | env-gated reset link | `test_endpoints.py` |
| NFR-SEC-07 | secrets via `.env` | repo scan + `.gitignore` review |
| NFR-SEC-08 | ABAC-gated endpoints | endpoint coverage audit |
| NFR-SEC-09 | org-scoped queries | `test_cases.py`, `test_tenancy.py` |
| NFR-SEC-10 | TLS at gateway | deployment config review |
| NFR-REL-01..05 | probes, fallback, persistence, kafka toggle | `test_endpoints.py`, fault-injection, integration tests |
| NFR-SCAL-01..04 | HPA, indexes, topic scheme, org partitioning | manifest + schema review |
| NFR-USE-01..05 | dashboard UX | UI tests / walkthrough |
| NFR-MAINT-01..05 | layering, typing, tests, config, docs | CI (pytest, tsc, vite build) |
| NFR-PORT-01..04 | PG/SQLite, container, K8s, topic contract | CI matrix + manifest dry-run (`k8s/` added) |

## Coverage gaps (next phases)

- **FR-TENANT-06, FR-UI-05/06** — incident-management, entity-graph
  visualization, SOAR automation, MITRE/threat-intel alert context, and the ML
  retraining pipeline (daily CronJob → `POST /retrain` hot-swap) are
  implemented. Remaining work: administrator cross-tenant views (FR-TENANT-06)
  in the UI plus the remaining FR-UI-05/06 screens (admin controls, audit-log +
  role states), and the live K8s rollout for PostgreSQL/Kafka.

## Notes on test file layout

- API/integration tests: `backend/tests/api/test_endpoints.py`
- Service/unit tests: `backend/tests/services/*` (`test_cases`, `test_entity_graph`,
  `test_soar`, `test_mitre`, `test_threat_intel`, `test_tenancy`, `test_ml_client`,
  `test_helpers`, `test_item_service`)
- ML contract tests: `backend/tests/contract/test_ml_contract.py`
