# AXIOM AI Demo — 5-Min Portfolio Walkthrough

> **AXIOM AI** — *Self-evident threat reasoning. Instant containment.* — http://localhost:3000 (`/brief` → `/case/1`)

This is the exact walkthrough for demonstrating AXIOM AI. Stack is `docker compose -f docker/docker-compose.yml up -d --build` (postgres + backend + ml-service + dashboard).

---

## 0. Opening (0:00-0:20) — Brand

- Show **http://localhost:3000/welcome** — AXIOM AI hero, 3-column Bento layout, posture score card, plain-English story, and instant blast-radius containment.
- Say: “AXIOM AI is the autonomous AI security analyst for growing companies — self-evident threat reasoning, zero alerts fatigue.”

## 1. Auth (0:20-0:50)

- Click **Get Started** → `/register` — note `BrandLogo` Axiom Delta mark + royal cobalt blue accents.
- Register `analyst / analyst@axiom.ai / ChangeMe#2026` (role ANALYST) → **Sign in** → `/login`.
- Login — lands on **AXIOM AI Brief** (`/brief`).

## 2. SOC Brief & Bento Layout (0:50-1:30)

- Show 3-Column Bento layout:
  - **Posture Score Card**: White card with royal cobalt ring displaying `96/100`.
  - **Latest Incident Card**: Midnight Navy card (`#0e1320`) with plain-English incident story narrative, blast-radius asset chips (`Server`, `User`, `IP`, `Application`), and `Remediate Incident` primary button.
  - **Recent Alerts & Operations**: Live event log and green `All Systems Operational` indicator.

## 3. Interactive Case & Ask-AXIOM AI Copilot (1:30-2:30)

- Click **View Case** → `/cases/1` — view plain-English incident story, blast radius connected assets graph, recommended action, and Ask-AXIOM AI interactive copilot chat.
- Ask copilot: *"What assets are affected in the blast radius?"* → AXIOM AI replies in real time with exact asset list and risk scores.
- Action Gate: Review recommended reversible action (`REVOKE_CREDENTIALS` / `BLOCK_SOURCE_IP`) → Click **Approve Action** → instant SOAR execution & audit logging.

## 4. Entity Graph & Threat Alerts (2:30-3:50)

- Open **Entity Graph** (`/entities`) — summary KPIs (nodes/edges/hub degree), **Path Finder** (From ID → To ID → Trace path), and entity blast-radius SVG view.
- Open **Threat Alerts** (`/alerts`) — searchable alerts list, MITRE technique mapping (`T1078`), and severity filters.

## 5. Security Connectors & SOAR Automation (3:50-4:40)

- **Security Connectors** — monitor live status for Okta Identity Cloud, CrowdStrike / Sentinel EDR, AWS GuardDuty, and Cloudflare WAF.
- **SOAR Automation** (`/soar`) — Dry-run rule evaluator, playbook executions, and reversible action logs.

## 6. Closing (4:40-5:00)

- “AXIOM AI combines self-evident LLM reasoning, blast radius graph tracking, and one-click reversible containment.”

---

## Local URLs

- Landing: http://localhost:3000/welcome
- Console: http://localhost:3000 (→ /brief after login)
- API: http://localhost:8000/health/live, http://localhost:8001/health
