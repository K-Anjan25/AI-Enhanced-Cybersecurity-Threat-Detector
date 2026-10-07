/**
 * Admin — `/admin` and its six panels (design.md §3, §4.8; T-410, T-422).
 *
 * All six of the design's children exist here now: users & roles, API keys,
 * connectors, thresholds, retention & GDPR, audit. Connectors was the last one — it
 * needed T-422's delivery read API behind it, and until then the index said so rather
 * than offering a tab that looked live.
 *
 * Sub-routes are real routes rather than in-page tabs, so a deep link works, the back
 * button works, and a 403 on one panel does not take the others down with it. The nav
 * inside the page is a list of `NavLink`s with `aria-current` — the same mechanism the
 * shell's rail uses, so a reader who learned one has learned both.
 *
 * Every panel is mounted lazily by the route, which is the point of splitting them:
 * opening `/admin` reads the directory, not the audit trail as well.
 */
import { type ReactNode } from 'react';
import { NavLink, Route, Routes } from 'react-router-dom';

import { ADMIN_SECTIONS, type AdminSectionPath } from '../../../components/layout/nav';
import { AuditPanel } from '../components/AuditPanel';
import { ConnectorsPanel } from '../components/ConnectorsPanel';
import { KeysPanel } from '../components/KeysPanel';
import { RetentionPanel } from '../components/RetentionPanel';
import { ThresholdsPanel } from '../components/ThresholdsPanel';
import { RolesPanel, UsersPanel } from '../components/UsersPanel';

interface Panel {
  /** What the panel answers, so the index page is a map rather than a menu. */
  summary: string;
  element: ReactNode;
}

/**
 * The addresses come from `nav.ts` and the panels from here.
 *
 * The addresses moved when the command palette needed the same list (T-411): a
 * second copy is how the palette offers a section this page does not have. The
 * record is keyed by the section union, so a section added without a panel — or a
 * panel for a section that no longer exists — is a type error rather than a blank
 * screen.
 */
const PANELS: Readonly<Record<AdminSectionPath, Panel>> = {
  users: {
    summary: 'Who exists, what each may do, and the rule that keeps one admin in place.',
    element: <UsersPanel />,
  },
  keys: {
    summary:
      'Machine credentials: issue one, read its prefix, revoke it. The secret is shown once.',
    element: <KeysPanel />,
  },
  connectors: {
    summary:
      'Outbound endpoints: where alerts are sent, the floor each receives at, one signed test event, and every attempt with its outcome.',
    element: <ConnectorsPanel />,
  },
  thresholds: {
    summary: 'The band edges in force, where each came from, and what a change would have done.',
    element: <ThresholdsPanel />,
  },
  retention: {
    summary: 'What a retention run would drop, what it cannot reach, and erasure with its ledger.',
    element: <RetentionPanel />,
  },
  audit: {
    summary: 'Every recorded change, filterable and exportable, with nothing that can edit it.',
    element: <AuditPanel />,
  },
};

const SECTIONS = ADMIN_SECTIONS.map((section) => ({
  path: section.path,
  to: section.to,
  label: section.label,
  icon: section.icon,
  ...PANELS[section.path],
}));

export function AdminPage() {
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-h1">Admin</h1>
        <p className="text-body-sm text-muted">
          Governance surfaces. Everything here is admin-only on the server and audited when it
          changes something (R-53, FR-42) — hiding a panel would not be the control; the API's own
          refusal is.
        </p>
      </header>

      <div className="flex flex-col gap-6 lg:flex-row">
        <nav aria-label="Admin sections" className="lg:w-rail lg:shrink-0">
          <ul className="flex flex-wrap gap-2 lg:flex-col">
            {SECTIONS.map((section) => (
              <li key={section.to}>
                <NavLink
                  to={section.to}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-control px-2 py-1 text-body ${isActive ? 'bg-surface text-accent' : 'text-ink hover:bg-surface'}`
                  }
                >
                  {/* 16 px, unlike the rail's 20: this is a dense list (§5.6) —
                      `py-1` rows of body text beside a panel, not one icon per
                      44 px row. `aria-hidden` for the same reason as the rail's:
                      the label is the link's name. */}
                  <section.icon aria-hidden="true" className="size-icon-sm shrink-0" />
                  {section.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0 flex-1">
          <Routes>
            <Route index element={<AdminIndex />} />
            {SECTIONS.map((section) => (
              <Route key={section.path} path={section.path} element={section.element} />
            ))}
            {/* The role matrix is a view of the users panel's own data, not a section
                of its own: it explains the roles the pickers above offer (R-53). */}
            <Route path="users/roles" element={<RolesPanel />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}

/** `/admin` itself: the map of what is behind each section. */
function AdminIndex() {
  return (
    <section aria-labelledby="admin-index-heading" className="flex flex-col gap-3">
      <h2 id="admin-index-heading" className="text-h2">
        Sections
      </h2>
      <ul className="flex flex-col gap-2">
        {SECTIONS.map((section) => (
          <li key={section.to} className="flex flex-col">
            <NavLink
              className="flex items-center gap-2 text-body text-accent underline"
              to={section.to}
            >
              <section.icon aria-hidden="true" className="size-icon-sm shrink-0" />
              {section.label}
            </NavLink>
            <span className="text-body-sm text-muted">{section.summary}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
