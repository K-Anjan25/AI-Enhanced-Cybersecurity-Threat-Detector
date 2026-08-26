# Frontend User Flow Diagrams

All diagrams use Mermaid syntax and render in supported documentation viewers.

---

## 1. Authentication Flow

```mermaid
flowchart TD
    A[User navigates to /login or /register] --> B{Is user authenticated?}
    B -- No --> C[Show login/register form]
    B -- Yes --> D[Redirect to /dashboard]
    
    C --> E[Submit credentials]
    E --> F{Valid credentials?}
    F -- No --> G[Flash error: "Invalid username or password"]
    G --> C
    F -- Yes --> H[Backend sets HttpOnly cookies: access_token, refresh_token]
    H --> I[GET /api/v1/auth/me → returns user payload]
    I --> J[React Query sets user cache]
    J --> K[Navigate to /dashboard]
    K --> L[Show dashboard with user context]
    
    style A fill:#0f0f0f, color:#f9fafb
    style K fill:#3b82f6, color:#fff
```

---

## 2. Alert Analysis Flow (Single Log Entry)

```mermaid
flowchart TD
    A[User pastes / uploads log entry] --> B[POST /api/v1/alerts/analyze]
    B --> C[ML service returns anomaly score + severity]
    C --> D[SecurityAlert record created in DB]
    D --> E[Realtime Kafka event (if enabled)]
    E --> F[Alert appears in Alerts list (auto-refetch)]
    F --> G[User clicks alert → detail view]
    
    style A fill:#0f0f0f, color:#f9fafb
    style F fill:#3b82f6, color:#fff
```

---

## 3. Incident / Case Management Flow

```mermaid
flowchart TD
    A[User views Alerts list] --> B[Click "Create Case" on alert]
    B --> C[POST /api/v1/cases/ with alert reference]
    C --> D[Case record created, linked to alert]
    D --> E[Case appears in Cases list with paginator]
    
    subgraph Case Details
        E --> F[User edits: status, priority, assignee, title, description]
        F --> G[PATCH /api/v1/cases/{case_id}]
        G --> H[Case updated, audit log entry created]
    end
    
    H --> I[Toast: "Case updated successfully"]
    I --> J[Return to Cases list or stay on detail view]
    
    style C fill:#10b981, color:#fff
    style G fill:#10b981, color:#fff
```

---

## 4. SOAR Evaluation & Trigger Flow

```mermaid
flowchart TD
    A[User selects alert → "Evaluate Manually"] --> B[POST /api/v1/soar/evaluate]
    B --> C[Backend queries active DetectionRules + SoarPlaybooks]
    C --> D[Rules engine matches alert dict → returns candidate actions]
    D --> E[Display: "X actions would fire" with expandable detail]
    
    subgraph Trigger Branch
        A2[User selects alert → "Trigger SOAR Response"] --> B2[POST /api/v1/soar/trigger/{alert_id}]
        B2 --> C2[Same rule/playbook evaluation]
        C2 --> F[Backend executes playbook actions (Kafka → SOAR platform)]
        F --> G[SOAR system executes playbook]
        G --> H[POST /api/v1/soar/actions → new audit record]
        H --> I[Toast: "SOAR response executed (X actions)"]
        I --> J[Refresh SOAR actions list]
    end
    
    style B fill:#f59e0b, color:#0f0f0f
    style B2 fill:#f59e0b, color:#0f0f0f
```

---

## 5. Entity Graph & MITRE Mapping Flow

```mermaid
flowchart TD
    A[User views Entities list] --> B[Click entity → detail view]
    B --> C[GET /api/v1/entities/{entity_id}]
    C --> D[Display: risk score, first_seen, last_seen, observed_attributes]
    
    subgraph Graph Navigation
        D --> E[User clicks "View Graph" → ENTITY_GRAPH_API]
        E --> F[GET /api/v1/entities/{entity_id}/graph?depth=N]
        F --> H[Render force-directed graph (nodes=entities, edges=relationships)]
        H --> I[Pan/zoom, node tooltip with MITRE technique tags]
        
        subgraph Path Finding
            I --> J[User clicks two entities → "Find Path"]
            J --> K[POST /api/v1/entities/path?from_id=X&to_id=Y]
            K --> L[BFS shortest path between entities]
            L --> M[Highlight path on graph, show risk delta]
        end
    end
    
    subgraph Reputation Override
        D --> N[User clicks "Adjust Risk Score"] --> O[POST /api/v1/entities/{entity_id}/reputation]
        O --> P[Analyst overrides risk_score, db commit]
        P --> Q[Entity card updates, toast: "Risk score updated"]
    end
    
    style C fill:#8b5cf6, color:#fff
    style F fill:#8b5cf6, color:#fff
```

---

## 6. Analytics / Trends Flow

```mermaid
flowchart TD
    A[User navigates to Analytics dashboard] --> B[GET /api/v1/analytics/overview]
    B --> C[Aggregated stats: total alerts, critical count, top threats]
    C --> D[Render: KPI cards (4 cards: total, critical, high, medium)]
    
    subgraph Trends
        A --> E[User selects "Trends" tab] --> F[GET /api/v1/analytics/trends?days=7]
        F --> G[Daily alert counts line chart (last N days)]
        G --> H[Update chart with new data refetch interval (30s)]
    end
    
    subgraph Top Threats
        A --> I[User selects "Top Threats" tab] --> J[GET /api/v1/analytics/top-threats?limit=10]
        J --> K[Bar chart: most common threat messages]
        K --> L[Update on refetch]
    end
    
    L --> M[User changes days picker → new API call]
    
    style C fill:#0f0f0f, color:#f9fafb
    style G fill:#0f0f0f, color:#f9fafb
```

---

## 7. Rules Management Flow

```mermaid
flowchart TD
    A[User navigates to Rules list] --> B[GET /api/v1/rules?page=1&limit=20]
    B --> C[Display table: rule name, severity, status, last triggered]
    
    subgraph Create
        B --> D[Click "New Rule"] --> E[Modal: form with rule conditions, severity, actions]
        E --> F[POST /api/v1/rules] --> G[Rule created, audit logged]
        G --> H[Toast: "Rule created"] --> I[Table refreshes, new rule appears]
    end
    
    subgraph Update
        C --> J[Click "Edit" on rule] --> K[Modal pre-filled with current rule data]
        K --> L[PUT /api/v1/rules/{rule_id}] --> M[Rule updated, audit logged]
        M --> M2[Toast: "Rule updated"] --> N[Table refreshes]
    end
    
    subgraph Delete
        C --> O[Click "Delete"] --> P[DELETE /api/v1/rules/{rule_id}] --> Q[Success: {"success": true}]
        Q --> R[Toast: "Rule deleted"] --> S[Table refreshes, rule removed]
    end
    
    style E fill:#3b82f6, color:#fff
    style K fill:#3b82f6, color:#fff
```

---

## 8. User Settings / Profile Flow

```mermaid
flowchart TD
    A[User clicks profile avatar → "Settings"] --> B[GET /api/v1/users/profile]
    B --> C[Display: username, email, role, clearance, department, organization]
    
    subgraph Profile Updates
        B --> D[User edits profile fields] --> E[PUT /api/v1/users/profile]
        E --> F[Backend validates, updates user record]
        F --> G[Toast: "Profile updated successfully"]
        G --> H[Return to profile view, cached data refreshed]
    end
    
    subgraph Password Change
        B --> I[User clicks "Change Password"] --> J[Open modal with current password + new password fields]
        I --> K[PUT /api/v1/users/updatePassword]
        K --> L[Backend validates current password, hashes new one, updates]
        L --> M[Toast: "Password changed. You are logged out."]
        M --> N[Auto-logout, redirect to /login]
    end
    
    style E fill:#10b981, color:#fff
    style K fill:#10b981, color:#fff
```

---

## 9. Multi-Tenant / Org Context Flow

```mermaid
flowchart TD
    A[Login flow sets org_id from default org (or onboarding wizard)] --> B[All API calls append ?org_id=... or use cookie-scoped session]
    B --> C[User switches org in header dropdown]
    C --> D[POST /api/v1/admin/switch-org {org_id}]
    D --> E[Backend sets session org_id cookie]
    E --> F[All subsequent API calls are org-scoped]
    F --> G[User sees data for new org; navigation persists]
    
    style A fill:#0f0f0f, color:#f9fafb
    style D fill:#8b5cf6, color:#fff
```

---

## 10. Data Export Flow

```mermaid
flowchart TD
    A[User clicks "Export Alerts" on Alerts page] --> B[GET /api/v1/alerts/export]
    B --> C[Backend streams CSV as StreamingResponse]
    C --> D[Browser triggers download: security_alerts.csv]
    D --> E[File contains: id, alert_type, source_ip, source, severity, score, message, created_at]
    
    style B fill:#0f0f0f, color:#f9fafb
```