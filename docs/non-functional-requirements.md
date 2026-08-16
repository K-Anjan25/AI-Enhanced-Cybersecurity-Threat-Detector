# Non-Functional Requirements

**System:** AI-Enhanced Cybersecurity Threat Detector (v3 target)
**Document type:** Non-Functional Requirements Specification (NFRS)

Each requirement has a stable ID (`NFR-xx`), a category, a **measurable target**
and a **verification method**. Targets are indicative baselines for the v3
reference deployment (Compose → K8s) and should be re-baselined under load test.

---

## 1. Performance & Capacity

| ID | Category | Requirement | Target | Verification |
| --- | --- | --- | --- | --- |
| NFR-PERF-01 | Latency | Alert analysis API latency (p95) | ≤ 500 ms per request (single record) | `GET /health`-timed load test (Locust/k6) |
| NFR-PERF-02 | Latency | Batch scan throughput | ≥ 100 log lines/sec in background task | timer around `POST /upload-logs` + `/uploads/{id}` |
| NFR-PERF-03 | Capacity | Concurrent scans | ≥ `MAX_CONCURRENT_SCANS` (default 10) without starvation | background-task soak test |
| NFR-PERF-04 | Capacity | Alert listing | paginated queries `?limit=100` ≤ 200 ms at 10k alerts | seeded-DB query benchmark |
| NFR-PERF-05 | Capacity | ML prediction throughput | ≥ 50 predictions/sec per ML replica | load test on `ml-service /predict/*` |

## 2. Security

| ID | Category | Requirement | Target | Verification |
| --- | --- | --- | --- | --- |
| NFR-SEC-01 | Auth | Passwords stored as salted hashes (bcrypt) | no plaintext / reversible hash | code review + schema inspection |
| NFR-SEC-02 | Auth | Access tokens short-lived; refresh rotation + JTI blocklist | access 30 min default | `POST /logout` then reuse → rejected |
| NFR-SEC-03 | Session | Cookies httpOnly, `SameSite=Strict`; `Secure` when `COOKIE_SECURE` | no JS-readable tokens | browser/network inspection |
| NFR-SEC-04 | Brute-force | Login rate limit + account lockout | 10/min per client; lockout at 5 failures | auth test suite + integration test |
| NFR-SEC-05 | Integrity | Audit log append-only | UPDATE/DELETE rejected at ORM | unit test raising on ORM update/delete |
| NFR-SEC-06 | Auth | Reset-link disclosure gated by environment | `reset_link` only when non-production | test asserting prod vs dev |
| NFR-SEC-07 | Hardening | Secrets via environment (`.env`), never committed | no secrets in repo | `git log` scan + `.gitignore` |
| NFR-SEC-08 | Authorization | Every protected endpoint permission-gated (ABAC) | no unguarded privileged routes | endpoint coverage audit |
| NFR-SEC-09 | Isolation | Tenant queries scoped to `org_id` | no cross-tenant reads | multi-org service tests |
| NFR-SEC-10 | Transport | TLS termination at gateway/proxy in production | HTTPS only | deployment config review |

## 3. Reliability & Availability

| ID | Category | Requirement | Target | Verification |
| --- | --- | --- | --- | --- |
| NFR-REL-01 | Uptime | Backend availability (production) | ≥ 99.5% | K8s probes + SLI monitoring |
| NFR-REL-02 | Health | Liveness + readiness probes | `/health/live`, `/health/ready` | probe tests in CI |
| NFR-REL-03 | Failover | ML service outage degrades gracefully | heuristic fallback, no 5xx for core analysis | fault-injection test (kill ml-service) |
| NFR-REL-04 | Durability | Upload history survives restart | `scan_batches` persisted | restart + `GET /uploads/{id}` test |
| NFR-REL-05 | Resiliency | Kafka outage doesn't break core REST flow | `ENABLE_KAFKA` toggle; publish failures non-fatal | integration test with broker down |

## 4. Scalability

| ID | Category | Requirement | Target | Verification |
| --- | --- | --- | --- | --- |
| NFR-SCAL-01 | Horizontal | Stateless API + ML services scale by replica | K8s HPA by CPU/RPS | deployment manifest review |
| NFR-SCAL-02 | Data | Relational data on PostgreSQL with indexes on hot columns | `org_id`, `ip_address`, `created_at`, `status` indexed | schema inspection |
| NFR-SCAL-03 | Streaming | Event backbone decouples producers/consumers | Kafka topics per domain | component diagram trace |
| NFR-SCAL-04 | Tenancy | Tenant isolation scales horizontally via `org_id` partitioning | no shared-tenant coupling | architecture review |

## 5. Usability

| ID | Category | Requirement | Target | Verification |
| --- | --- | --- | --- | --- |
| NFR-USE-01 | Onboarding | Login/register complete in ≤ 2 steps | 1 form each | UI walkthrough |
| NFR-USE-02 | Feedback | Dashboard actions show success/error feedback | immediate toast/inline | manual UI test |
| NFR-USE-03 | Comprehension | KPI + severity distribution visible without drilling | first paint of analytics page | UI test |
| NFR-USE-04 | Context | Each alert shows MITRE ATT&CK + threat-intel context | detail view / columns | UI test |
| NFR-USE-05 | Responsiveness | Dashboard responsive down to 768px | no horizontal scroll | viewport test |

## 6. Maintainability

| ID | Category | Requirement | Target | Verification |
| --- | --- | --- | --- | --- |
| NFR-MAINT-01 | Modularity | Services layered: api → service → model | no controller SQL | lint rule / review |
| NFR-MAINT-02 | Typing | Backend type-hinted; dashboard TypeScript strict | `tsc` clean | CI typecheck |
| NFR-MAINT-03 | Tests | Core paths covered by automated tests | backend pytest green; dashboard `tsc + vite build` green | CI |
| NFR-MAINT-04 | Config | All tuning via `Settings` env vars | no hardcoded thresholds in services | config review |
| NFR-MAINT-05 | Docs | Diagrams + requirements kept in sync with code | update-on-change policy | review in PR |

## 7. Portability & Interoperability

| ID | Category | Requirement | Target | Verification |
| --- | --- | --- | --- | --- |
| NFR-PORT-01 | DB | SQLAlchemy models run on PostgreSQL (prod) + SQLite (tests) | schema compatible | CI matrix |
| NFR-PORT-02 | Container | Backend/ML/dashboard containerized | `docker build` green | CI image build |
| NFR-PORT-03 | K8s | v3 deployable via manifests/Helm on K8s | ready for `kubectl apply` | manifest dry-run |
| NFR-PORT-04 | Interop | Events published in domain-topic scheme consumable by third-party tools | topic contract stable | schema review |
