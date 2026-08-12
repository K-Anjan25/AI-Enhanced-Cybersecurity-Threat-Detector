# Sequence Diagram — Login → Dashboard → Alert Ingest

> UML **Sequence Diagram**: two core flows —
> (A) authentication + dashboard bootstrap, and
> (B) log upload → ML prediction → alert persistence.

```mermaid
sequenceDiagram
    autonumber
    participant U as Analyst
    participant R as React SPA
    participant A as FastAPI /auth
    participant P as ABAC Policy
    participant D as Postgres
    participant ML as ML Service :8001
    participant E as Engine (services)

    U->>R: Enter credentials
    R->>A: POST /login (username+password)
    A->>D: verify user + bcrypt compare
    alt valid
        A-->>R: access_token + refresh_token + role
        Note over A,R: COOKIE_AUTH: also sets httpOnly SameSite cookies
        R->>A: GET /me (Bearer or cookie)
        A->>P: subject_permissions(user)
        P-->>A: permission set
        A-->>R: user + roles + permissions
        R->>R: store role + perms only (JWT stays httpOnly/XSS-safe)
        R-->>U: Dashboard shell (nav filtered by perms)
        R->>A: GET /alerts
        A->>P: require auth (alerts:read gate)
        A->>D: query SecurityAlert desc
        A-->>R: serialized alerts
        R-->>U: render AlertList
    else invalid
        A-->>R: 401 "Invalid credentials"
        R-->>U: show error
    end

    U->>R: Upload log file
    R->>A: POST /upload-logs (multipart)
    A->>D: INSERT ScanBatch (status=pending)
    A-->>R: 202 {batch_id, status=pending}
    R-->>U: "Scanning in background..."
    A->>E: BackgroundTask: run_scan_batch(batch_id)
    E->>D: ScanBatch.status = processing
    loop each record
        E->>ML: POST /predict/log
        alt ML unreachable
            ML-->>E: (fallback) heuristic classification
        end
        alt is_anomaly
            E->>D: INSERT SecurityAlert
            E->>D: INSERT ScannedAlert (evidence row)
        end
    end
    E->>D: ScanBatch.status = completed, threats_detected
    loop poll until terminal
        R->>A: GET /uploads/{batch_id}
        A-->>R: batch status
    end
    R->>R: reload /logs/history (from scan_batches)
```

## Notes

- **Single source of truth is Postgres.** Every read (alerts, stats, history,
  audit) is a direct SQL query; there is no in-memory snapshot cache, so there
  is no risk of a multi-worker "cache divergence". Writes persist to Postgres
  and are immediately visible to all workers/processes.
- **Uploads are async.** `POST /upload-logs` returns immediately with a
  `batch_id`; the ML scan runs in a FastAPI `BackgroundTasks` worker and the
  dashboard polls `GET /uploads/{batch_id}` until the batch is `completed` or
  `failed`. Upload history is persisted in the `scan_batches` table.
- **Auth tokens.** `access_token`/`refresh_token` are short-lived JWTs issued
  on `/login` and re-issued by `/refresh`. With `COOKIE_AUTH` enabled the
  backend additionally stores them in httpOnly SameSite cookies (XSS-safe); the
  Bearer-header transport stays supported for API clients. `/me` returns the
  authenticated user's roles and ABAC permission set.
- **ML failure path.** If `POST /predict/log` errors, `ml_client` retries with
  backoff (2 attempts) then falls back to heuristic keyword/volume scoring, so
  the upload still completes and the result is tagged `fallback: true`.