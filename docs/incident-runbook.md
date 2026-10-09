# AEGIS Incident Runbook

## Quick Reference

| Symptom                  | Likely Cause               | First Action                         |
| ------------------------ | -------------------------- | ------------------------------------ |
| Dashboard shows no data  | Backend unhealthy          | Check `docker compose logs backend`  |
| Alerts stopped appearing | Kafka consumer stuck       | Check consumer lag in Grafana        |
| Drift page shows all red | Model serving data shifted | Check `/api/v1/detection/status`     |
| 503 errors from API      | PostgreSQL down            | Check `docker compose logs postgres` |
| High error rate          | Service overloaded         | Check resource usage, scale up       |

## Incident Response Procedures

### INC-01: Backend Unavailable

**Symptoms:** Dashboard shows "connection refused", health probes fail.

**Steps:**

1. Check container status: `docker compose ps backend`
2. Check logs: `docker compose logs backend --tail=100`
3. Common causes:
    - **Database connection failed**: Check PostgreSQL is running and accessible
    - **Port conflict**: Another process on port 8000
    - **Configuration error**: Check environment variables
4. Restart: `docker compose restart backend`
5. If persistent: `docker compose down && docker compose up -d --build backend`

**Escalation:** If backend crashes on startup, check for Python import errors in logs.

---

### INC-02: No Alerts Being Generated

**Symptoms:** Alerts page empty despite active traffic.

**Steps:**

1. Verify capture services are running: `docker compose ps | grep -E "tcpdump|zeek|suricata|tshark"`
2. Check detection status: `curl http://localhost:8000/api/v1/detection/status`
3. Check if flows are being ingested: `curl http://localhost:8000/metrics | grep aegis_flows`
4. Check ML service: `curl http://localhost:8001/health`
5. If ML service down: `docker compose restart ml-service`

**Root causes:**

- Capture services not capturing (interface not available in Docker)
- Detection engine not started (check backend startup logs)
- ML service unreachable (check Docker network)

---

### INC-03: High Consumer Lag

**Symptoms:** Grafana shows `aegis_consumer_lag > 10,000`.

**Steps:**

1. Check Kafka: `docker compose logs kafka --tail=50`
2. Check if scoring workers are running
3. Scale workers (Kubernetes): `kubectl scale deployment/aegis-scoring-worker --replicas=5 -n aegis`
4. If Kafka is down: `docker compose restart kafka`
5. Workers will resume from committed offsets (no data loss)

---

### INC-04: Drift Alert (PSI > 0.25)

**Symptoms:** Grafana alert "AEGISDriftPSIHigh", Drift page shows red bars.

**Steps:**

1. Check which feature drifted: `curl http://localhost:8000/metrics | grep aegis_drift_psi`
2. Review recent traffic patterns in the Traffic page
3. If legitimate change (e.g., new service deployed):
    - Document the change
    - Consider retraining the model with new baseline
4. If suspicious (e.g., sudden shift in port distribution):
    - Investigate for scanning or exfiltration
    - Check recent alerts for correlated activity

---

### INC-05: Database Unavailable

**Symptoms:** API returns 503, `docker compose logs postgres` shows errors.

**Steps:**

1. Check PostgreSQL container: `docker compose ps postgres`
2. Check disk space: `docker exec postgres df -h /var/lib/postgresql/data`
3. Restart: `docker compose restart postgres`
4. If data corruption: restore from backup using `ops/backup-restore.sh restore`

**Impact:** Read requests fail with 503. Scoring continues (writes to Kafka). No data loss.

---

### INC-06: ML Service Crash Loop

**Symptoms:** ML service restarting repeatedly.

**Steps:**

1. Check logs: `docker compose logs ml-service --tail=100`
2. Common causes:
    - **Out of memory**: Increase memory limit in docker-compose.yml
    - **Model file missing**: Check model artifacts are present
    - **Port conflict**: Another process on port 8001
3. Restart: `docker compose restart ml-service`
4. Backend falls back to rule-based detection automatically

---

## Post-Incident

After resolving any incident:

1. Document timeline and root cause in incident log
2. File tasks for any preventive measures
3. Update this runbook if the procedure was incomplete
4. Review metrics to confirm system is healthy: `curl http://localhost:8000/api/v1/detection/status`
