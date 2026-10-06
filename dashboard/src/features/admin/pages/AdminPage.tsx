/**
 * Admin — `/admin` and its five panels (design.md §3, §4.8; T-410).
 *
 * The design's navigation tree gives Admin six children. Five of them exist here —
 * users & roles, API keys, thresholds, retention & GDPR, audit — and the sixth,
 * connectors, has no task row and no screen yet, so it renders the honest "not built"
 * state rather than a tab that looks live (see `App.tsx`'s `PENDING`; T-422 files it).
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

import { AuditPanel } from '../components/AuditPanel';
import { KeysPanel } from '../components/KeysPanel';
import { RetentionPanel } from '../components/RetentionPanel';
import { ThresholdsPanel } from '../components/ThresholdsPanel';
import { RolesPanel, UsersPanel } from '../components/UsersPanel';

interface Section {
  /** The path relative to `/admin`, which is what `Routes` needs. */
  path: string;
  /** The absolute href, which is what the nav and the index list need. */
  to: string;
  label: string;
  /** What the panel answers, so the index page is a map rather than a menu. */
  summary: string;
  element: ReactNode;
}

const SECTIONS: readonly Section[] = [
  {
    path: 'users',
    to: '/admin/users',
    label: 'Users & roles',
    summary: 'Who exists, what each may do, and the rule that keeps one admin in place.',
    element: <UsersPanel />,
  },
  {
    path: 'keys',
    to: '/admin/keys',
    label: 'API keys',
    summary:
      'Machine credentials: issue one, read its prefix, revoke it. The secret is shown once.',
    element: <KeysPanel />,
  },
  {
    path: 'thresholds',
    to: '/admin/thresholds',
    label: 'Thresholds',
    summary: 'The band edges in force, where each came from, and what a change would have done.',
    element: <ThresholdsPanel />,
  },
  {
    path: 'retention',
    to: '/admin/retention',
    label: 'Retention & GDPR',
    summary: 'What a retention run would drop, what it cannot reach, and erasure with its ledger.',
    element: <RetentionPanel />,
  },
  {
    path: 'audit',
    to: '/admin/audit',
    label: 'Audit log',
    summary: 'Every recorded change, filterable and exportable, with nothing that can edit it.',
    element: <AuditPanel />,
  },
];

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
                    `block rounded-control px-2 py-1 text-body ${isActive ? 'bg-surface text-accent' : 'text-ink hover:bg-surface'}`
                  }
                >
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
            <NavLink className="text-body text-accent underline" to={section.to}>
              {section.label}
            </NavLink>
            <span className="text-body-sm text-muted">{section.summary}</span>
          </li>
        ))}
        <li className="flex flex-col">
          <span className="text-body text-muted">Connectors</span>
          <span className="text-body-sm text-muted">
            Not built yet: design.md §3 lists the route, the backlog has no task for the screen
            until T-422. The API that would back it exists — webhook endpoints with a signing secret
            shown once — so this is a screen gap, not a service one.
          </span>
        </li>
      </ul>
    </section>
  );
}
