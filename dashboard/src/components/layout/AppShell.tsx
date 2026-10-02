/**
 * Application shell: persistent left nav rail plus top bar (design.md §3).
 *
 * The rail is 240px and collapses to a 56px icon rail. Route guards are cosmetic
 * here — the server enforces authorisation (rule R-52).
 */
import { useState, type ReactNode } from 'react';
import { NavLink, Outlet } from 'react-router-dom';

import { useTheme } from '../../theme/ThemeProvider';
import { ConnectionStatus, type ConnectionState } from '../ui/ConnectionStatus';

interface NavItem {
  to: string;
  label: string;
  section: string;
}

/** Information architecture from design.md §3. */
const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', label: 'Overview', section: 'Monitor' },
  { to: '/alerts', label: 'Alerts', section: 'Threats' },
  { to: '/traffic', label: 'Traffic', section: 'Explore' },
  { to: '/logs', label: 'Logs', section: 'Explore' },
  { to: '/hunt', label: 'Hunt', section: 'Explore' },
  { to: '/models', label: 'Models', section: 'Models' },
  { to: '/admin', label: 'Admin', section: 'Admin' },
];

interface AppShellProps {
  /** Connection state for the top-bar indicator. */
  connection?: ConnectionState;
  children?: ReactNode;
}

export function AppShell({ connection = 'live', children }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(false);
  const { theme, toggleTheme } = useTheme();

  const sections = [...new Set(NAV_ITEMS.map((item) => item.section))];

  return (
    <div className="flex min-h-screen bg-base text-ink">
      <nav
        aria-label="Primary"
        className={`flex flex-col border-r border-line bg-surface transition-[width] duration-200 ${
          collapsed ? 'w-12' : 'w-16'
        }`}
        style={{ width: collapsed ? 56 : 240 }}
      >
        <div className="flex h-8 items-center justify-between px-4">
          {!collapsed ? <span className="text-h2">AEGIS</span> : null}
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
            className="rounded-input p-1 text-muted hover:text-ink"
          >
            {collapsed ? '\u00BB' : '\u00AB'}
          </button>
        </div>

        {sections.map((section) => (
          <div key={section} className="mt-4">
            {!collapsed ? (
              <p className="px-4 text-caption uppercase tracking-wide text-muted">{section}</p>
            ) : null}
            <ul>
              {NAV_ITEMS.filter((item) => item.section === section).map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    title={item.label}
                    className={({ isActive }) =>
                      `block px-4 py-2 text-body ${
                        isActive ? 'border-l-2 border-accent text-ink' : 'text-muted'
                      } hover:text-ink`
                    }
                  >
                    {collapsed ? item.label.slice(0, 1) : item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-8 items-center justify-between border-b border-line bg-surface px-6">
          <span className="text-caption text-muted">
            AI-Enhanced Cybersecurity Threat Detector
          </span>
          <div className="flex items-center gap-4">
            <ConnectionStatus state={connection} />
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              className="rounded-input border border-line px-3 py-1 text-caption hover:text-accent"
            >
              {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
          </div>
        </header>

        <main className="flex-1 p-6">{children ?? <Outlet />}</main>
      </div>
    </div>
  );
}
