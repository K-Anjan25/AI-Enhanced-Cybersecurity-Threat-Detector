# AXIOM AI — Brand Identity & Design System Specification

> **⚠ Superseded:** the product ships as **NOCTRA** ("Night Shift" identity,
> Lumen violet). The current specification is
> [`noctra-redesign-spec.md`](noctra-redesign-spec.md). This AXIOM AI document
> is retained as the Phase 20 historical decision record.

## 1. Brand Overview & Strategy

- **Brand Name**: `AXIOM AI`
- **Tagline**: *Self-evident threat reasoning. Instant containment.*
- **Core Positioning**: An autonomous AI security analyst for small and growing companies (*"You employ an analyst, you don't operate a complex dashboard"*).
- **Core Value Proposition**: Synthesizes multi-source telemetry (Okta, CrowdStrike/SentinelOne, AWS GuardDuty, Cloudflare) into plain-English incident story briefs, maps affected blast-radius entity graphs, and drafts reversible remediation actions for one-click human approval.

---

## 2. Brand Mark & Symbol Geometry

- **Logo Mark Symbol**: An interlocking geometric Axiom Delta symbol combined with a protective cobalt blue shield and central AI intelligence node.
- **Color Accent**: Royal Cobalt Blue (`#2563eb`) on dark midnight background or light slate.
- **SVG Definition**:
  ```xml
  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
    <rect width="32" height="32" rx="8" fill="#0e1320" />
    <path d="M16 3 L28 11 V21 L16 29 L4 21 V11 Z" stroke="#2563eb" stroke-width="1.8" fill="rgba(37, 99, 235, 0.12)" />
    <path d="M16 7 L23 21 H9 Z" stroke="#2563eb" stroke-width="1.5" fill="none" />
    <path d="M11.5 17 H20.5" stroke="#2563eb" stroke-width="1.5" stroke-linecap="round" />
    <circle cx="16" cy="14" r="2.2" fill="#2563eb" />
  </svg>
  ```

---

## 3. Brand Typography Stack

| Typography Layer | Font Family | Usage |
|---|---|---|
| **Display / Headlines** | `Sora Variable` | Page headers, hero titles, score metrics, wordmark |
| **UI Body / Prose** | `Inter Variable` | Incident stories, rationale text, button labels, navigations |
| **Technical Telemetry** | `JetBrains Mono Variable` | Hostnames, IPv4/IPv6 addresses, MITRE tags, SOAR action IDs, hashes |

---

## 4. Color Palette & Token Specification

| Color Token | Hex Code | Visual Role |
|---|---|---|
| **App Canvas Light** | `#f4f6fa` | Main page background (soft slate off-white) |
| **Embedded Card Navy** | `#0e1320` | Midnight navy contrast bento cards |
| **Posture Score White** | `#ffffff` | Pure white posture score card |
| **Cobalt Primary** | `#2563eb` | Score ring, primary action buttons, brand logo |
| **Status Emerald** | `#10b981` | Platform operational dot, reversible undo badge |
| **Status Warning** | `#f59e0b` | High priority alerts, decision pending badges |
| **Status Critical** | `#ef4444` | Critical severity pills, emergency lockout |
| **Text Slate Dark** | `#0f172a` | Primary headlines and high-contrast text |

---

## 5. UI Layout Architecture (Bento 3-Column Grid)

1. **Column 1 — Security Posture Score Card (White)**:
   - Displays clean title `Security Posture Score`.
   - Central cobalt blue ring chart (`#2563eb`) with `96/100`.
   - Health status: `Overall Health: Good`.
2. **Column 2 — Center Incident Card (Midnight Navy `#0e1320`)**:
   - `LATEST INCIDENT` tag, plain-English narrative story.
   - `Affected Assets (Blast Radius):` chips (`Server`, `User`, `IP`, `Application`).
   - Primary `Remediate Incident` button in royal cobalt blue (`#2563eb`).
3. **Column 3 — Triage & Status Cards (Midnight Navy `#0e1320`)**:
   - `RECENT ALERTS` list with timestamps (`SQL Injection Attempt` 14:15, `Suspicious API Activity` 13:58, `Network Scan` 13:30).
   - `PLATFORM STATUS` green dot: `All Systems Operational`.
