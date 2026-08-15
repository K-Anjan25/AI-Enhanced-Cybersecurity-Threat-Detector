# State Diagram — Alert & Incident Lifecycle

> UML **State Machine Diagram** (behavioral) for the two key stateful entities:
> the persisted upload `ScanBatch` and the incident `Case`.

## ScanBatch (upload job)

```mermaid
stateDiagram-v2
    [*] --> pending : POST /upload-logs
    pending --> processing : background task starts
    processing --> completed : batch fully analyzed
    processing --> failed : ML unreachable & no fallback
    completed --> [*]
    failed --> [*]
    pending --> failed : DB write error
```

## Case (incident)

```mermaid
stateDiagram-v2
    [*] --> open : create_case (linked to source alert optional)
    open --> triaging : analyst triages (PATCH status)
    triaging --> open : re-opened after review
    triaging --> resolved : containment + eradication done
    resolved --> triaging : regressed / reopened
    resolved --> closed : archived (final state)
    closed --> [*]

    note right of open : org-scoped (org_id), ABAC-guarded
    note right of resolved : audited via CASE_UPDATED audit log
```

## State transitions enforced by `case_service`

| From | To | Trigger | ABAC permission |
| --- | --- | --- | --- |
| `open` | `triaging` | analyst assigns / starts work | `alerts:write` |
| `triaging` | `resolved` | containment complete | `alerts:write` |
| `resolved` | `triaging` | regression detected | `alerts:write` |
| `resolved` | `closed` | archival (final) | `alerts:write` |
| any | any | invalid transition | rejected (`ValueError` → 400) |

> **Current state:** `ScanBatch.status` transitions are implemented in
> `alert_service.process_batch`; `Case.status` transitions are implemented in
> `case_service.update_case` (valid set: `open | triaging | resolved | closed`).
