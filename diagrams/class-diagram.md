# Class Diagram — Backend Domain

> UML **Class Diagram** of the core backend classes (SQLAlchemy models + policy + services).

```mermaid
classDiagram
    class Org {
        +int id
        +str name
        +str slug
        +datetime created_at
    }
    class User {
        +int id
        +int org_id
        +str username
        +str email
        +str password
        +str profile_image
        +bool is_active
        +bool is_blocked
        +str role
        +int clearance_level
        +str department
        +int failed_login_attempts
        +datetime created_at
    }
    class SecurityAlert {
        +int id
        +int org_id
        +str alert_type
        +str source_ip
        +str severity
        +float score
        +str message
        +str mitre_tactic
        +str mitre_technique_id
        +str mitre_technique
        +datetime created_at
    }
    class ScannedAlert {
        +int id
        +int org_id
        +str filename
        +str threat_type
        +str raw_log
        +str risk
    }
    class ScanBatch {
        +int id
        +int org_id
        +str filename
        +int total_logs
        +int threats_detected
        +str status
        +str message
    }
    class Case {
        +int id
        +int org_id
        +str title
        +str description
        +str status
        +str priority
        +int source_alert_id
        +int assignee_id
        +int created_by_id
        +datetime created_at
        +datetime updated_at
    }
    class Entity {
        +int id
        +int org_id
        +str entity_type
        +str value
        +float risk_score
        +int occurrences
        +dict meta
        +datetime first_seen
        +datetime last_seen
    }
    class EntityLink {
        +int id
        +int org_id
        +int source_entity_id
        +int target_entity_id
        +str relation
        +int source_alert_id
    }
    class SoarAction {
        +int id
        +int org_id
        +str action_id
        +str action_type
        +str severity
        +str rule_name
        +int alert_id
        +dict payload
        +str status
    }
    class TokenBlocklist {
        +int id
        +str jti
    }
    class DetectionRule {
        +int id
        +str name
        +str severity
        +bool is_active
    }
    class IpReputation {
        +int id
        +str ip_address
        +float threat_score
        +bool is_blocked
    }
    class EngineSetting {
        +int id
        +str key
        +str value
    }
    class AuditLog {
        +int id
        +str action
        +str actor
        +str resource
        +str details
    }
    class MITRE {
        +dict map_alert(alert_type, message)
    }
    class ThreatIntel {
        +dict enrich_alert(db, source_ip)
    }
    class EntityGraph {
        +list extract_entities(message, source_ip)
        +Entity upsert_entity(db, type, value, org_id)
        +index_alert(db, alert)
        +dict entity_graph(db, id, depth, org_id)
    }
    class Soar {
        +list evaluate_alert(alert, rules)
        +list respond_to_alert(db, alert, rules)
        +dict execute_action(db, alert, matched)
    }
    class ABAC {
        +bool can(user, permission, resource)
        +set subject_permissions(user)
        +int effective_clearance(user)
        +require_permission(perm)
    }
    class AuthService {
        +get_access_token(subject) str
        +get_refresh_token(subject) str
        +verify_password(plain, hash) bool
    }
    class Services {
        +process_log(log, kafka, org_id) dict
        +process_batch(logs, filename, org_id) dict
        +create_case(payload, actor, org_id) Case
        +update_case(case, payload, actor) Case
        +get_alert_stats(db) dict
        +update_engine_settings(db, payload)
        +create_rule(db, data)
        +upsert_ip_reputation(db, data)
        +create_audit_log(db, action)
    }

    Org "1" --> "0..*" User
    Org "1" --> "0..*" SecurityAlert
    Org "1" --> "0..*" ScannedAlert
    Org "1" --> "0..*" ScanBatch
    Org "1" --> "0..*" Case
    Org "1" --> "0..*" Entity
    Org "1" --> "0..*" SoarAction
    User "1" --> "0..*" SecurityAlert
    User "1" --> "0..*" ScannedAlert
    User "1" --> "0..*" ScanBatch
    Case "0..1" --> "1" SecurityAlert : source_alert
    SecurityAlert "1" --> "0..*" SoarAction : triggers
    SecurityAlert "1" --> "0..*" Entity : establishes
    Entity "1" --> "0..*" EntityLink : source
    Entity "1" --> "0..*" EntityLink : target
    User ..> ABAC : evaluated by
    ABAC ..> AuthService
    Services ..> ABAC : permission gates
    Services --> MITRE
    Services --> ThreatIntel
    Services --> EntityGraph
    Services --> Soar
    Services --> SecurityAlert
    Services --> ScanBatch
    Services --> Case
    Services --> EngineSetting
    Services --> AuditLog
    Services --> DetectionRule
    Services --> IpReputation
```

## Model mapping (SQLAlchemy → table)

| Class | Table | Notes |
| --- | --- | --- |
| `Org` | `orgs` | tenant; `slug` unique; `ensure_default_org` seeds `default` |
| `User` | `users` | ABAC subject attrs: `role`, `clearance_level`, `department`; FK → `orgs.id` |
| `SecurityAlert` | `security_alerts` | engine detections; FK → `users.id`, `orgs.id`; MITRE tactic/technique |
| `ScannedAlert` | `scanned_alerts` | per-finding evidence rows from uploaded log files; FK → `users.id`, `orgs.id` |
| `ScanBatch` | `scan_batches` | persisted upload history (filename, counts, status); FK → `users.id`, `orgs.id` |
| `Case` | `cases` | incident lifecycle (`open → triaging → resolved → closed`); FK → `orgs.id`, `security_alerts.id` |
| `Entity` | `entities` | attack-graph nodes; unique `(org_id, entity_type, value)` |
| `EntityLink` | `entity_links` | attack-graph edges; FK → `entities.id` (×2), `security_alerts.id` |
| `SoarAction` | `soar_actions` | automated-response audit; `action_id` unique; FK → `orgs.id`, `security_alerts.id` |
| `TokenBlocklist` | `token_blocklist` | JTI revocation on logout (no user FK by design) |
| `DetectionRule` | `detection_rules` | name-unique rules |
| `IpReputation` | `ip_reputation` | threat_score + blacklist |
| `EngineSetting` | `engine_settings` | key/value singletons |
| `AuditLog` | `audit_logs` | immutable admin/triage trail (actor is a snapshot string, no FK) |

## Service layer API surface (`backend/app/services/*`)

- `user_service.py` — `get_profile_data`, `update_user_profile_data`, `update_user_password`
- `alert_service.py` — `process_log`, `get_alert_stats`, `get_top_threats`
- `item_service.py` — engine settings CRUD, rules CRUD, IP reputation CRUD, `audit` wrapper
- `case_service.py` — `create_case`, `update_case`, `list_cases`, `get_case` (org-scoped)
- `mitre.py` — `map_alert` → MITRE ATT&CK tactic/technique
- `threat_intel.py` — `enrich_alert` → source-IP reputation context
- `entity_graph.py` — `extract_entities`, `upsert_entity`, `index_alert`, `entity_graph`
- `soar.py` — `evaluate_alert`, `respond_to_alert`, `execute_action`
- `ml_client.py` — `predict_network`, `predict_log`, batch variants (retry + heuristic fallback)
- `kafka_producer.py` / `kafka_consumer.py` — optional stream plumbing