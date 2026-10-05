# PRD — AI-Enhanced Cybersecurity Threat Detector

| | |
|---|---|
| **Codename** | AEGIS |
| **Document** | Product Requirements Document |
| **Version** | 0.1 (foundation) |
| **Last updated** | 2026-10-02 |
| **Status** | Approved for build — no code exists yet |
| **Related** | [architecture.md](architecture.md) · [rules.md](rules.md) · [design.md](design.md) · [task.md](task.md) · [memory.md](memory.md) |

---

## 1. Objective

Build a system that uses **transformer models** to analyse **network traffic** and **system logs** in order to detect anomalies and **predict potential cybersecurity threats before they materialise into confirmed incidents**.

The product is a detection and triage platform, not a prevention appliance. It ingests telemetry, scores behavioural windows, raises ranked alerts with human-readable explanations, and gives an analyst the evidence needed to confirm or dismiss each alert in under a minute.

## 2. Problem Statement

**Who has the problem.** Security operations teams in small-to-mid organisations (5–50 person SOC, or a single security lead in a smaller company).

**What the problem is.** Signature-based IDS/IPS and static threshold rules miss novel, low-and-slow, and behaviourally-normal-looking attacks. Analysts drown in thousands of low-confidence alerts per day, so real signals get buried. Mean time to detect (MTTD) for insider abuse and reconnaissance activity is measured in days or weeks, not minutes.

**Why now.** Transformer architectures have proven effective on sequential and semi-structured data — exactly the shape of flow records and log lines — and open benchmark datasets (UNSW-NB15, CIC-IDS2017) make supervised baselines reproducible without proprietary telemetry.

**Technical problem solved.** Improve security posture by proactively identifying and mitigating risk, reducing the likelihood of a successful cyber attack.

### Measurable outcomes

| Outcome | Metric | Baseline (typical) | Target at v1.0 |
|---|---|---|---|
| Faster detection | Median time from first malicious flow to alert | hours–days | ≤ 5 seconds |
| Less noise | Alerts per analyst per day requiring action | 200+ | ≤ 40 |
| Trustworthy signal | Precision on `high`/`critical` alerts | — | ≥ 0.80 |
| Coverage | Recall on benchmark attack families | — | ≥ 0.90 |
| Explainability | Alerts with a human-readable top-3 reason | 0% | 100% |

## 3. Scope

### 3.1 In scope for v1.0

**Both** telemetry types, because they cover complementary failure modes and the fusion of the two is the product's differentiator.

| Domain | What is analysed | Source of truth for v1 |
|---|---|---|
| Network traffic | NetFlow/Zeek-style flow records: 5-tuple, protocol, packet/byte counts, duration, flags, window, inter-arrival | UNSW-NB15, CIC-IDS2017, plus synthetic generator |
| System logs | Auth logs, auditd, syslog, application logs, firewall deny logs | HDFS/BGL-style public log corpora + synthetic generator |

**Threat families targeted** (explicit goals):

| ID | Threat family | Detection signal | Example labels |
|---|---|---|---|
| T1 | Reconnaissance / port scanning | Burst of distinct destination ports per source, abnormal flow shape | `Reconnaissance`, `PortScan` |
| T2 | DoS / DDoS | Flow-rate and packet-size distribution shift, half-open ratio | `DoS Hulk`, `DDoS`, `Heartbleed` |
| T3 | Exploitation & malware delivery | Payload-length and flag anomalies, shellcode-like flows | `Exploits`, `Shellcode`, `Backdoor` |
| T4 | Credential abuse / brute force | Repeated auth failures per identity, then success from new host | `Brute Force`, `Generic` |
| T5 | Insider threat / privilege escalation | Off-hours access, new privilege use, unusual file/API sequences | log-derived labels |
| T6 | Exfiltration & C2 beaconing | Periodic outbound beaconing, volume asymmetry, jitter collapse | `Exfiltration`, `Botnet` |

### 3.2 Explicitly out of scope for v1.0

- Inline blocking / traffic dropping. Detection and alerting only; response is delegated to the customer's firewall via webhook.
- Deep packet inspection of encrypted payloads. We use flow metadata and log semantics, never payload decryption.
- Endpoint detection (EDR), EDR telemetry ingestion, process-tree analysis.
- Phishing-email NLP and URL reputation scoring.
- Multi-tenant SaaS billing, self-serve signup, metering.
- Automated remediation / SOAR playbooks that touch production hosts.
- Adversarial-evasion hardening research (documented as a known limitation, not a solved problem).

Anything in this list moves to the `BACKLOG` section of [task.md](task.md), never silently into the build.

## 4. Users and personas

| Persona | Role | Primary job to be done | Frequency |
|---|---|---|---|
| **Ana — SOC Analyst (Tier 1)** | Investigates alerts | "Tell me what happened, show me the evidence, let me close it in under 60 seconds." | Continuous, shift-based |
| **Raj — Security Lead (Tier 2/3)** | Hunts, tunes, owns policy | "Let me query raw telemetry, tune thresholds, and prove coverage to my CISO." | Daily |
| **Priya — CISO / Engineering Manager** | Owns risk posture | "Give me a defensible trend and a coverage story I can report upward." | Weekly |
| **Dev — Platform Engineer** | Deploys and operates AEGIS | "Let me deploy it in a container, feed it, and see its health without reading the model code." | Ad hoc |

## 5. Functional requirements

Priority: **M** = must for v1.0, **S** = should, **C** = could.

### 5.1 Ingestion

| ID | P | Requirement |
|---|---|---|
| FR-01 | M | Accept flow records via `POST /api/v1/ingest/flows` as JSON or NDJSON batches up to 1,000 records/request. |
| FR-02 | M | Accept log lines via `POST /api/v1/ingest/logs` as JSON or NDJSON batches up to 5,000 lines/request. |
| FR-03 | M | Accept the same two payload shapes over Kafka topics `flows.raw` and `logs.raw` for streaming deployments. |
| FR-04 | M | Validate every record against a versioned schema (`flow@1`, `log@1`); reject with a per-record error list, never fail the whole batch. |
| FR-05 | M | Persist raw ingested records for a configurable retention window (default 30 days) so alerts remain reproducible. |
| FR-06 | S | Provide a synthetic generator CLI that produces labelled normal and attack traffic for demos and tests. |
| FR-07 | S | Provide a bulk import CLI for UNSW-NB15 and CIC-IDS2017 CSV/PCAP-derived CSV. |

### 5.2 Analysis and detection

| ID | P | Requirement |
|---|---|---|
| FR-10 | M | Build sliding behavioural windows per entity (default: last 50 flows per source host, 200 log lines per host+service). |
| FR-11 | M | Score every closed window with the flow transformer model and the log transformer model. |
| FR-12 | M | Produce a composite threat score in `[0,1]` from late fusion of both models. |
| FR-13 | M | Map score to a severity band: `critical` ≥ 0.90, `high` ≥ 0.75, `medium` ≥ 0.55, `low` ≥ 0.35, `info` below. |
| FR-14 | M | Attach top-3 contributing features or log templates as a human-readable explanation to every alert. |
| FR-15 | M | Suppress duplicate alerts for the same (entity, threat family) within a configurable cool-down (default 15 min). |
| FR-16 | M | Allow an analyst to mark any alert `true_positive`, `false_positive`, or `benign`, and persist that feedback. |
| FR-17 | S | Support an on-demand single-window analysis endpoint for what-if investigation. |
| FR-18 | S | Persist analyst feedback and use it to recompute per-tenant alert thresholds weekly. |
| FR-19 | C | Correlate a flow alert with a log alert on the same entity within ±60s into one grouped case. |

### 5.3 Alerting and response

| ID | P | Requirement |
|---|---|---|
| FR-20 | M | Push new alerts to the dashboard over a WebSocket channel with a REST/SSE fallback. |
| FR-21 | M | Send alerts to an outbound webhook (HMAC-signed body, retry with backoff) for `high` and `critical` severities. |
| FR-22 | M | Provide `GET /api/v1/alerts` with filtering by severity, threat family, entity, time range, status. |
| FR-23 | S | Export alert batches to CSV and PDF for reporting. |

### 5.4 Model operations

| ID | P | Requirement |
|---|---|---|
| FR-30 | M | Serve at least two independently versioned models (flow model, log model) with immutable model IDs. |
| FR-31 | M | Expose per-model evaluation metrics (precision, recall, F1, ROC-AUC, PR-AUC) on a held-out temporal split. |
| FR-32 | M | Compute population stability index (PSI) per feature on incoming traffic and flag drift above 0.25. |
| FR-33 | S | Support zero-downtime model swap: promote a new version, route traffic, roll back in one call. |
| FR-34 | S | Log a full training manifest (dataset hashes, config, git SHA, metrics) for every trained artifact. |

### 5.5 Authentication, authorisation and administration

| ID | P | Requirement |
|---|---|---|
| FR-40 | M | Authenticate users with email/password (Argon2id) issuing short-lived JWT access tokens plus refresh tokens. |
| FR-41 | M | Enforce RBAC with four roles: `viewer`, `analyst`, `responder`, `admin`. |
| FR-42 | M | Record every mutating action in an append-only audit log (actor, action, target, timestamp, source IP). |
| FR-43 | S | Support OIDC SSO for enterprise deployments. |
| FR-44 | S | Support scoped API keys for machine-to-machine ingestion. |

### 5.6 Visualisation

| ID | P | Requirement |
|---|---|---|
| FR-50 | M | Overview dashboard: alert volume, severity mix, top attacked entities, live detection status. |
| FR-51 | M | Alert triage view: evidence, timeline, explanation, related raw records, one-click verdict. |
| FR-52 | M | Traffic explorer: time-series of flows and scores, plus an entity relationship graph. |
| FR-53 | S | Model ops view: metrics over time, drift gauges, version comparison. |
| FR-54 | S | Hunt console: free-text and structured query over raw logs and flows. |

Full page-level specification lives in [design.md](design.md).

## 6. Non-functional requirements

| ID | Area | Requirement |
|---|---|---|
| NFR-01 | Latency | p95 in-process scoring latency ≤ 150 ms per window on 4 vCPU; end-to-end ingest→alert ≤ 5 s at p95. |
| NFR-02 | Throughput | ≥ 5,000 flow records/s and ≥ 10,000 log lines/s per API worker, horizontally scalable. |
| NFR-03 | Availability | 99.5% monthly for the API; the ingestion path degrades to Kafka buffering when scoring is down. |
| NFR-04 | Scalability | Stateless API workers; all state in PostgreSQL / Elasticsearch / Kafka. Horizontal scale by replica count. |
| NFR-05 | Privacy | GDPR-aligned: configurable retention, per-record PII redaction for user fields, right-to-erasure endpoint. |
| NFR-06 | Security | TLS in transit, encryption at rest for the datastore, secrets from env/secret manager only, OWASP ASVS L2 baseline. |
| NFR-07 | Observability | Prometheus metrics, structured JSON logs, distributed traces on ingest→score→alert, health/readiness probes. |
| NFR-08 | Portability | Runs unmodified via `docker compose` on Linux/macOS; Kubernetes manifests for production. |
| NFR-09 | Accessibility | Dashboard meets WCAG 2.1 AA (contrast ≥ 4.5:1, full keyboard operation, screen-reader labels). |
| NFR-10 | Determinism | Given identical inputs and a pinned model ID, scoring output is byte-identical. No wall-clock or random seeding in the inference path. |
| NFR-11 | Maintainability | ≥ 80% line coverage on backend business logic; all public modules typed. |
| NFR-12 | Cost | Full local dev stack runs on a 16 GB laptop; no paid external API is required for any core feature. |

## 7. Data sources

| Dataset | Use | Facts recorded | Source |
|---|---|---|---|
| **UNSW-NB15** | Primary network training/eval set | 2,540,044 records; 49 packet- and flow-based features; 9 attack families | [research.unsw.edu.au/projects/unsw-nb15-dataset](https://research.unsw.edu.au/projects/unsw-nb15-dataset) |
| **CIC-IDS2017** | DDoS/DoS, brute force, web-attack coverage; held-out generalisation test | Multi-day PCAP + labelled flows across five attack scenarios | [unb.ca/cic/datasets/ids-2017.html](https://www.unb.ca/cic/datasets/ids-2017.html) |
| **HDFS / BGL log corpora** | Log-anomaly model training and evaluation | Public system-log benchmark corpora | See [memory.md](memory.md#data-sources) |
| **Synthetic generator** (ours) | Insider-threat and beaconing scenarios absent from the above; deterministic tests; demos | Built by us, fully labelled by construction | [task.md](task.md) — T-106 |

Datasets are large and are **never committed to Git**. They are downloaded into `data/raw/` (gitignored) by a fetch script with checksum verification. See rule R-40 in [rules.md](rules.md).

## 8. Success metrics

**Model quality** (measured on the temporal held-out split, reported per release):

- ROC-AUC ≥ 0.97 and PR-AUC ≥ 0.92 on UNSW-NB15 flows.
- Precision ≥ 0.80 and recall ≥ 0.90 on the union of attack families at the deployed `high` threshold.
- Cross-dataset transfer: trained on UNSW-NB15, evaluated on CIC-IDS2017 — recall must not fall below 0.70. This is the honesty test against overfitting.
- False-positive rate on benign-only days ≤ 0.5%.

**Product quality:**

- Median analyst time-to-verdict on an alert ≤ 60 s (instrumented in the UI).
- ≥ 70% of analyst verdicts agree with the model's top-1 threat family.
- Zero `critical` alerts shipped without an explanation block.

**Engineering quality:**

- CI green on every merge; backend coverage ≥ 80%; frontend type-check clean.
- Local `docker compose up` to a working dashboard in under 5 minutes from a clean clone.

## 9. Release plan

| Milestone | Contents | Exit criteria |
|---|---|---|
| **M0 — Foundations** | Repo structure, docs, CI, Docker skeleton, synthetic generator | `docker compose up` serves a health endpoint; CI runs lint+test |
| **M1 — Data & baseline** | Datasets fetched, preprocessing, feature schema, logistic-regression + gradient-boosting baselines | Baseline PR-AUC recorded in [memory.md](memory.md) as the bar to beat |
| **M2 — Transformer models** | Flow-sequence transformer and log-sequence transformer, training pipeline, evaluation harness | Both models beat their baselines on the temporal split |
| **M3 — Serving & API** | Model service, REST + WebSocket API, alert store, RBAC, audit log | Alerts flow end-to-end from synthetic traffic to an authenticated API response |
| **M4 — Dashboard** | Overview, triage, traffic explorer, model ops | Analyst can complete the triage loop in the UI on live data |
| **M5 — Hardening & ship** | Load test, drift monitoring, docs, Kubernetes manifests, security review | All NFRs verified with evidence attached to the release note |

Task-level detail in [task.md](task.md).

## 10. Risks and mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| **False positives destroy analyst trust** | Fatal for adoption | High | Per-tenant threshold calibration from feedback (FR-18); ship `medium`/`low` muted by default; track FP rate as a release gate. |
| **Benchmark overfitting** — great scores on UNSW-NB15, useless in the field | High | High | Mandatory cross-dataset evaluation; temporal (not random) splits; synthetic hold-out set built independently. |
| **Data leakage between train and test** | High | Medium | Split by time and by source entity; a leakage audit is an acceptance criterion on T-203. |
| **Detection latency misses the NFR budget** | Medium | Medium | Benchmark from M2 onward; quantised / ONNX-exported inference path as a documented fallback. |
| **Datasets are 2015–2017 vintage** | Medium | High | Frame v1 as architecture validation; document modern-traffic retraining as the first production task. |
| **Adversarial evasion** (attacker shapes traffic to look benign) | High | Medium | Documented limitation in the release note; ensemble disagreement surfaced as a signal; not claimed as solved. |
| **The system itself becomes a target** | High | Medium | Threat model in [architecture.md](architecture.md#12-security-of-the-system-itself); least-privilege service accounts; alert data is sensitive by definition. |
| **Scope creep toward a full SIEM/SOAR** | High | High | Section 3.2 is authoritative; scope changes require a PRD version bump and a decision entry in [memory.md](memory.md). |

## 11. Assumptions

1. The deployment environment can supply NetFlow/Zeek or equivalent flow records. If not, the synthetic generator stands in for demos.
2. Log sources emit parseable timestamped lines; unparseable lines are counted and surfaced, not silently dropped.
3. Class imbalance is handled in training (sampling + loss weighting), not by discarding data.
4. A single v1.0 model pair is shared across tenants; per-tenant fine-tuning is post-v1.
5. v1.0 is deployed on-premises or in a customer cloud account. AEGIS never exfiltrates telemetry to a third party.

## 12. Open questions

Tracked live in [memory.md](memory.md#open-questions). Currently unresolved:

1. Should the log model use a pretrained encoder (DistilBERT) or a from-scratch transformer over Drain3-mined log templates? Decision owner: model lead, due before T-204.
2. Is Elasticsearch justified at v1.0, or does PostgreSQL with partitioning suffice for the hunt console? Decision due before T-305.
3. What is the accepted false-positive budget in absolute alerts/day for the reference customer? Needed to set the default threshold.

## 13. Learning resources

Core references for the team. Verified links are in the table; the rest are canonical project home pages.

| Topic | Resource |
|---|---|
| Transformers | Hugging Face Transformers documentation — https://huggingface.co/docs/transformers |
| Deep learning framework | PyTorch tutorials — https://pytorch.org/tutorials/ |
| Network dataset | UNSW-NB15 — https://research.unsw.edu.au/projects/unsw-nb15-dataset |
| Network dataset | CIC-IDS2017 — https://www.unb.ca/cic/datasets/ids-2017.html |
| Model pattern | LogBERT: log anomaly detection via BERT — https://arxiv.org/abs/2103.04475 |
| Model pattern | TabTransformer for tabular data — https://arxiv.org/abs/2012.06678 |
| Serving | FastAPI — https://fastapi.tiangolo.com/ |
| Streaming | Apache Kafka documentation — https://kafka.apache.org/documentation/ |
| Observability | Prometheus — https://prometheus.io/docs/introduction/overview/ |
| Book | *Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow*, Aurélien Géron (O'Reilly) |
| Course | Coursera Cybersecurity specializations — https://www.coursera.org/ |

## 14. Why this project matters

- **Relevance.** Attack complexity is rising; AI-driven detection is in demand across the industry.
- **Innovation.** Applying transformer sequence modelling to combined flow and log telemetry, rather than to a single modality, is a genuinely current approach.
- **Impact.** Proactive detection has direct, quantifiable value: every hour shaved off MTTD reduces breach cost.
- **Skill showcase.** The build spans ML engineering, full-stack development, streaming infrastructure, and security domain knowledge.

## 15. Change log

| Date | Version | Change | Author |
|---|---|---|---|
| 2026-10-02 | 0.1 | Initial PRD written from the project brief. Repository reset to documentation-only. | AEGIS team |
