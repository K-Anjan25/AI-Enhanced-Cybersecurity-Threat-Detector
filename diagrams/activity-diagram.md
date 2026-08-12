# Activity Diagram — Threat Detection Pipeline

> UML **Activity Diagram** (behavioral) for the end-to-end log → alert →
> incident flow, covering the ML fallback path and multi-tenant scoping.

```mermaid
flowchart TD
    A([Log / Flow arrives]) --> B{Valid tenant?}
    B -- no --> X([Reject / quarantine])
    B -- yes --> C[Normalize + enrich<br/>raw-logs / raw-flows]
    C --> D[ML prediction<br/>predict_log / predict_network]
    D --> E{ML service reachable?}
    E -- no --> F[Heuristic fallback<br/>fallback: True]
    E -- yes --> F
    F --> G{Anomaly?}
    G -- no --> H[Publish events.normalized]
    H --> Z([End: benign])
    G -- yes --> I[Score -> severity]
    I --> J[MITRE ATT&CK mapping<br/>map_alert → tactic/technique]
    J --> K[Persist SecurityAlert<br/>org_id-scoped]
    K --> L[Publish alerts.raised]
    L --> M{Needs response?}
    M -- auto --> N[Execute action<br/>actions.executed]
    M -- analyst --> O[Create Case<br/>linked to source alert]
    O --> P[Triage → Resolve → Close<br/>PATCH /cases/{id}]
    P --> Q[Audit trail<br/>CASE_UPDATED]
    N --> Q
    Q --> Z
```

## Decision points

| Node | Decision | Output |
| --- | --- | --- |
| B | tenant resolved from `org_id` (JWT claim / header) | reject or proceed |
| E | ML service health + retry budget (2 retries, 0.3/0.6 s backoff) | ML result or heuristic |
| G | `is_anomaly` from prediction/fallback | normalize vs. alert |
| M | rule `is_active` + severity threshold | `actions.executed` or case creation |

> **Current state:** nodes A–K and N are implemented (`ml_client.py` fallback,
> `mitre.map_alert`, `alert_service.process_log` with `org_id`). Case creation
> (O–P) is live via the `cases` router; automated action execution (N) is the
> next phase (SOAR).
