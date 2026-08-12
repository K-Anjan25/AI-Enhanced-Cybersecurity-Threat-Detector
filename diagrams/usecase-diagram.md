# Use Case Diagram — SOC Console

> UML **Use Case Diagram** of the functional requirements.

```mermaid
flowchart TB
    a1(["<b>Analyst</b>"])
    a2(["<b>Admin</b>"])
    a3(["<b>User (self-registered)</b>"])
    a4(["System /<br/>Log Source"])

    s1["Log in / Register"]
    s2["Reset forgotten password"]
    s3["View threat alerts & details"]
    s4["Upload log files for scanning"]
    s5["View upload history"]
    s6["View analytics & trends"]
    s7["Update profile / password"]
    s8["Manage users<br/>(create, delete, roles, block)"]
    s9["Configure engine settings"]
    s10["View system audit logs"]
    s11["Manage detection rules / IP reputation"]

    a1 --> s1 --> s2
    a1 --> s3
    a1 --> s4 --> s5
    a1 --> s6
    a1 --> s7
    a3 --> s1
    a3 --> s3
    a3 --> s6

    a2 --> s1
    a2 --> s8
    a2 --> s9
    a2 --> s10
    a2 --> s11
    a4 --> s4
```

## ABAC enforcement per use case

| Use case | Backend permission gate | Notes |
| --- | --- | --- |
| Login / Register | public (`/login`, `/register`) | self-registration capped at `USER`/`ANALYST`; ADMIN rejected |
| Reset password | public (`/forgot-password`, `/reset-password`) | purpose-validated JWT; dev `reset_link` when SMTP off |
| View alerts | `get_current_user` (auth) | `alerts:read` implicit for all roles |
| Upload logs | `get_current_user` | ANALYST + ADMIN |
| View analytics | `get_current_user` | all roles |
| Manage users | `users:read/write/manage` | read/write = ADMIN; clean/delete = `users:manage` |
| Engine settings | `engine:read` (GET) / `engine:update` (PUT) | update needs clearance ≥ 4 (ADMIN) |
| Audit logs | `audit:read` | needs clearance ≥ 4 (ADMIN) |
| Rules / reputation | `rules:read`, `rules:write`, `rules:delete`; `reputation:read/write/block` | write/block need clearance ≥ 3 |

> All `require_permission` dependencies live in `backend/app/core/abac.py`; the
> permission catalog is `PERMISSIONS`, role base-sets are `ROLE_PERMISSIONS`,
> and clearance thresholds are `CLEARANCE_REQUIREMENTS`.