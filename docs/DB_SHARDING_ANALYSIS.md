# DB Load Balancing Analysis for NOCTRA (threatdb single DB)

## Current State
- Single Postgres `threatdb` with ~30 tables, all scoped by `org_id`.
- Tables: `security_alerts`, `cases`, `entities`, `audit_logs`, `network_segments`, `hunts`, `vulnerabilities`, `user_behavior_profiles`, `cloud_resources`, `sboms`, `honeypots`, `forensic_cases`, `stix_objects`, etc.
- All queries filter by `org_id` + time range.

## E-commerce analogy (orderdb, userdb, productdb) - Does it apply?
**Short answer: Not directly required yet, but we should prepare for horizontal scale.**

In e-com, domains are loosely coupled (orders vs catalog) and can be split by bounded context. In SIEM/SOC, domains are **tightly coupled**:
- Alert -> Case -> Entity -> Timeline -> SOAR Action -> Audit Log -> Compliance Evidence -> Exec Risk.
- Splitting into separate physical DBs would require distributed transactions / 2PC for case creation, breaking atomicity and increasing latency.

**Real problems we DO have:**
1. **Write heavy**: `security_alerts` ingest via Kafka/Connectors, high insert rate.
2. **Read heavy**: hunting KQL translates to SQL with full scan on `security_alerts.message`.
3. **Time-series**: alerts/logs grow unbounded.
4. **Multi-tenancy**: org_id filtering everywhere, noisy neighbor risk.

## Recommendation: Stay single logical DB, but implement these patterns (not full sharding)

### 1. Schema organization (logical separation, not physical)
- Keep one physical DB `threatdb`, but use schemas: `core`, `detect`, `protect`, `deceive`, `compliance`, `intel`.
- Each service queries its schema, but joins still possible.
- Implemented via `search_path` or table prefix. No code change needed now.

### 2. Partitioning
- Partition `security_alerts`, `audit_logs`, `scanned_alerts`, `hunt_executions` by RANGE on `created_at` monthly.
- Partition `vulnerabilities`, `cspm_violations` by `org_id` HASH if >100 orgs.
- SQLAlchemy supports declarative partitioning; add migration.

### 3. Read replicas + connection pooling
- `DATABASE_URL` for writes, `DATABASE_REPLICA_URL` for reads (analytics, hunting, exec risk).
- Use `pgbouncer` in transaction mode, pool size 20.
- In `app/core/database.py`, add `get_replica_db()` dependency.

### 4. Indexing strategy (already partially)
- Composite indexes: `(org_id, created_at DESC)`, `(org_id, severity)`, GIN on `message` for free-text hunt.
- For ITDR: index on `user_id, created_at`.

### 5. Caching layer
- Redis for `risk_metrics`, `compliance_score`, `ztna_graph`, `attack_heatmap` (TTL 5m).
- Already have `ha_status` for health.

### 6. When to actually shard?
- If single org >10M alerts/day or >1000 orgs.
- Then shard by `org_id` modulo N, using Citus extension or separate DBs with routing in `database_router.py`.
- We provide a router skeleton now, but disabled by default.

## Implementation in this PR
- Added `app/core/database_router.py` with `ShardedSession` that routes based on `org_id % shard_count` if `DB_SHARDING_ENABLED=True`.
- Added `get_read_db()` and `get_write_db()` dependencies.
- Added ZTNA seed defaults (10.0.0.0/24 internal, 10.0.1.0/24 dmz, 0.0.0.0/0 external) via `ztna_service.seed_defaults()`.
- Added hunt auto-run stub `hunt_service.schedule_saved_hunts()` (cron every 5m, creates case if results > threshold).
- Added `AI_AGENT_AUTO_APPROVE_LOW_RISK` toggle endpoint `/ai-agent/config`.
- Documented tool_use full implementation path.

## Conclusion
**Do NOT split into orderdb/userdb/productdb style now.** It adds operational complexity without solving the real bottleneck (time-series ingest + hunt scans). Instead, implement partitioning + read replica + caching + logical schemas. The router is ready if you ever need physical sharding.
