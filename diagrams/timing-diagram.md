# Timing Diagram — Login, Rate Limit & Session Lifecycle

> UML **Timing Diagram** (behavioral) for the v3 auth hardening: login
> rate-limiting, brute-force lockout, cookie session refresh, and token
> revocation. Time flows left → right; state bands show each subject's state.

## Login attempt window (rate limit + lockout)

```mermaid
timeline
    title Login window (60 s) — rate limit + brute-force lockout
    t0 Client : POST /login #1
    t1 Server : verify OK → set httpOnly cookie
    t2 Client : 4 more rapid POSTs
    t3 Server : rate limit budget 5/min → 5th blocked 429
          : failed attempts >= LOGIN_MAX_ATTEMPTS → is_blocked = true
    t4 Client : further POSTs → 403 "account locked"
</mermaid>
```

## State lifelines over time

```mermaid
sequenceDiagram
    autonumber
    actor U as Analyst
    participant GW as Gateway
    participant AU as Auth Service
    participant DB as PostgreSQL
    participant ML as ML Service

    Note over U,ML: Session lifecycle (COOKIE_AUTH=true)
    U->>GW: POST /login (username + password)
    GW->>AU: forward auth
    AU->>DB: verify failed_login_attempts, is_blocked
    alt account locked or rate limit exceeded
        AU-->>U: 429 / 403 (no token issued)
    else valid
        AU->>DB: reset failed_login_attempts
        AU-->>U: Set-Cookie access_token (httpOnly, SameSite=Strict) + refresh_token
        U->>GW: GET /alerts (cookie)
        GW->>AU: resolve user via cookie
        AU->>DB: tenant = org_id from subject
        AU-->>U: 200 data (org-scoped)
    end
    U->>GW: POST /logout
    GW->>AU: revoke refresh JTI → token_blocklist
    AU-->>U: clear cookies
```

## Timing bands

| Band | Initial state | Trigger | New state |
| --- | --- | --- | --- |
| Auth session | anonymous | `POST /login` OK | authenticated (cookie) |
| Rate-limit budget | 5/min | each login POST | -1; resets after 60 s |
| Account lockout | `is_blocked=False` | ≥ `LOGIN_MAX_ATTEMPTS` failures | `is_blocked=True` |
| Refresh token | valid | expiry / `/refresh` | rotated (new JTI) |
| Token blocklist | empty | `POST /logout` | JTI revoked until expiry |
| ML fallback | healthy call | 2 retries exhausted | heuristic prediction |

> **Current state:** login rate limit + lockout (`login_limiter`,
> `failed_login_attempts`, `is_blocked`), httpOnly cookie auth with
> `SameSite=Strict`, refresh-token JTI revocation, and the ML retry→heuristic
> fallback are all implemented.