/**
 * Application shell: persistent left nav rail plus top bar (design.md §3), and the
 * one place the realtime connection is shown (T-405).
 *
 * The rail is 240px and collapses to a 56px icon rail. Route guards are cosmetic
 * here — the server enforces authorisation (rule R-52).
 *
 * The connection is read from the realtime provider, so there is one answer to
 * "are we live?" for the whole app: the header indicator carries the label and
 * §8.1's stale age, and the banner below it explains the fallback. The `connection`
 * prop stays as an override for a story or a test that wants a state without a
 * socket; nothing in the app passes it.
 *
 * **The rail follows §8.3, and so does whether it is there at all.** Between 1024 and
 * 1439 px it *starts* collapsed to icons ("nav rail collapses to icons by default"),
 * with the toggle still available — an operator on a laptop gets the width back for
 * the table and can ask for the labels. Below 768 px it is not rendered at all: the
 * triage loop is the whole offered console, and a rail listing screens that would
 * answer with a notice is worse than no rail. Both come from the same viewport answer
 * the routes and the palette read, so the chrome and the pages cannot disagree about
 * which side of a boundary the window is on.
 *
 * The top bar carries global search (§3), which is the palette's visible affordance:
 * a keyboard-only feature that nothing points at is a feature only its author uses.
 * Both the rail's header row and the top bar are `h-topbar` — §3's 56 px — so they
 * line up; they were `h-8` (32 px) until T-411 put a control in the bar and the
 * height the design asks for became the height the bar needed.
 */
import { useState, type ReactNode } from 'react';
import { LogOut, PanelLeftClose, PanelLeftOpen, Search, ShieldCheck } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';

import { PALETTE_KEY_SHORTCUTS, paletteKeyLabel } from '../../lib/keyboard';
import { useViewportClass } from '../hooks/viewport';
import { NarrowNotice } from './NarrowNotice';
import { useTheme } from '../../theme/ThemeProvider';
import { ConnectionBanner } from '../realtime/ConnectionBanner';
import { useConnectionView } from '../realtime/useConnectionView';
import { ConnectionStatus, type ConnectionState } from '../ui/ConnectionStatus';
import { NAV_ITEMS } from './nav';

interface AppShellProps {
  /** Connection state for the top-bar indicator. */
  connection?: ConnectionState;
  /**
   * Opens the command palette.
   *
   * The shell does not own the palette: it renders the top bar's search control and
   * says what that control does. Where the palette lives and which keys open it are
   * the app's business, and a shell that imported the palette would be a shell that
   * could not be rendered without one.
   */
  onOpenPalette: () => void;
  onSignOut: () => void;
  children?: ReactNode;
}

export function AppShell({ connection, onOpenPalette, onSignOut, children }: AppShellProps) {
  // `null` is "nobody has said", which is what lets the default follow the window:
  // §8.3's icon rail on a laptop, labels on a large monitor. Once the operator
  // toggles it their choice sticks, including across a resize — a rail that sprang
  // back to its default under the cursor would be the shell arguing with them.
  const [collapsedByHand, setCollapsedByHand] = useState<boolean | null>(null);
  const { theme, toggleTheme } = useTheme();
  const view = useConnectionView(connection);
  const viewport = useViewportClass();
  const narrow = viewport === 'narrow';
  const collapsed = collapsedByHand ?? viewport === 'medium';

  const sections = [...new Set(NAV_ITEMS.map((item) => item.section))];

  return (
    <div className="flex min-h-screen bg-base text-ink">
      {/* Cyberpunk static grid — zero JS */}
      <div className="cyber-grid-bg" aria-hidden="true" />

      {narrow ? null : (
        <nav
          aria-label="Primary"
          // The widths are design.md §3's 240 px rail and 56 px icon rail, now
          // tokens (`w-rail`, `w-rail-collapsed`, T-402) instead of a class the
          // inline style then overrode.
          className={`flex flex-col border-r border-line bg-surface transition-[width] duration-panel ${
            collapsed ? 'w-rail-collapsed' : 'w-rail'
          }`}
        >
          <div className="flex h-topbar items-center justify-between px-4">
            {!collapsed ? <span className="text-h2">AEGIS</span> : null}
            <button
              type="button"
              onClick={() => setCollapsedByHand(!collapsed)}
              aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
              className="rounded-input p-1 text-muted hover:text-ink"
            >
              {/* The toggle is drawn, not spelled (§5.6): it used to render a pair
                  of guillemets — French quotation marks — which a screen reader
                  reads as punctuation and which say nothing about a rail, and which
                  `nav.test.ts` now scans the source for. The two panel icons are the
                  pair every editor uses for the same control, and the button's own
                  label already names the action. */}
              {collapsed ? (
                <PanelLeftOpen aria-hidden="true" className="size-icon-md" />
              ) : (
                <PanelLeftClose aria-hidden="true" className="size-icon-md" />
              )}
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
                        `flex items-center gap-2 px-4 py-2 text-body ${
                          collapsed ? 'justify-center' : ''
                        } ${
                          isActive ? 'border-l-2 border-accent text-ink' : 'text-muted'
                        } hover:text-ink`
                      }
                    >
                      {/* 20 px in the rail (§5.6: not a dense context — one icon per
                          row, 44 px tall). `aria-hidden`, because the label beside
                          it is the link's name; when the rail is collapsed the same
                          label is still in the link, as `sr-only` text, so the icon
                          is never the only content (§5.6) and the accessible name of
                          an entry does not change with the rail's width. */}
                      <item.icon aria-hidden="true" className="size-icon-md shrink-0" />
                      <span className={collapsed ? 'sr-only' : ''}>{item.label}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-topbar items-center justify-between border-b border-line bg-surface px-6">
          <span className="text-caption text-muted">AI-Enhanced Cybersecurity Threat Detector</span>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={onOpenPalette}
              aria-keyshortcuts={PALETTE_KEY_SHORTCUTS}
              className="flex items-center gap-2 rounded-input border border-line bg-base px-3 py-1 text-caption text-muted hover:text-ink"
            >
              <Search aria-hidden="true" className="size-icon-sm" />
              Search
              <kbd className="font-mono">{paletteKeyLabel()}</kbd>
            </button>
            <ConnectionStatus state={view.state} detail={view.detail} />
            <span className="hidden items-center gap-1 rounded-pill border border-line px-2 py-1 text-caption text-muted lg:inline-flex">
              <ShieldCheck aria-hidden="true" className="size-icon-sm text-accent" />
              Authenticated
            </span>
            <button
              type="button"
              onClick={onSignOut}
              aria-label="Sign out"
              className="inline-flex items-center gap-2 rounded-input border border-line px-3 py-1 text-caption text-muted hover:text-ink"
            >
              <LogOut aria-hidden="true" className="size-icon-sm" />
              <span className="hidden xl:inline">Sign out</span>
            </button>
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              className="rounded-input border border-line px-3 py-1 font-mono text-caption hover:text-accent"
            >
              {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
          </div>
        </header>

        {/* §8.3's banner. Above the connection banner, because it describes the whole
            window rather than a stream that is down. */}
        {narrow ? <NarrowNotice showQueueLink /> : null}

        {view.banner === null ? null : (
          <ConnectionBanner
            state={view.state}
            message={view.banner.message}
            explanation={view.banner.explanation}
            onRetry={view.retryNow}
          />
        )}

        <main className="flex-1 p-6">{children ?? <Outlet />}</main>
      </div>
    </div>
  );
}
