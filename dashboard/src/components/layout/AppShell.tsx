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
import { LogOut, Menu, Search } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';

import { PALETTE_KEY_SHORTCUTS, paletteKeyLabel } from '../../lib/keyboard';
import { useViewportClass } from '../hooks/viewport';
import { NarrowNotice } from './NarrowNotice';
import { useTheme } from '../../theme/ThemeProvider';
import { NAV_ITEMS } from './nav';
import { AegisLogo } from '../brand/AegisLogo';

interface AppShellProps {
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

/** Routes that open below 768 px (design.md §8.3: triage only). */
const NARROW_OFFERED: ReadonlySet<string> = new Set(['/alerts']);

export function AppShell({ onOpenPalette, onSignOut, children }: AppShellProps) {
  // `null` is "nobody has said", which is what lets the default follow the window:
  // §8.3's icon rail on a laptop, labels on a large monitor. Once the operator
  // toggles it their choice sticks, including across a resize — a rail that sprang
  // back to its default under the cursor would be the shell arguing with them.
  const [collapsedByHand, setCollapsedByHand] = useState<boolean | null>(null);
  const { theme, toggleTheme } = useTheme();
  const viewport = useViewportClass();
  const narrow = viewport === 'narrow';
  const collapsed = collapsedByHand ?? viewport === 'medium';
  // Below 768 px only triage opens (the `Offered` gate in App.tsx), so the drawer
  // lists only the entries that open. Listing the others would send a phone to
  // a "Not offered" page.
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navItems = narrow ? NAV_ITEMS.filter((item) => NARROW_OFFERED.has(item.to)) : NAV_ITEMS;
  const sections = [...new Set(navItems.map((item) => item.section))];

  return (
    <div className="flex min-h-screen flex-col bg-base text-ink">
      {/* The header spans the full width, above the sidebar and the content. */}
      <header className="flex h-topbar items-center gap-4 border-b border-line bg-base px-6">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <button
            type="button"
            onClick={() => (narrow ? setDrawerOpen(!drawerOpen) : setCollapsedByHand(!collapsed))}
            aria-expanded={narrow ? drawerOpen : !collapsed}
            aria-controls="primary-navigation"
            aria-label={
              narrow
                ? drawerOpen
                  ? 'Close navigation'
                  : 'Open navigation'
                : collapsed
                  ? 'Expand navigation'
                  : 'Collapse navigation'
            }
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-input text-muted hover:text-ink focus-visible:ring-2"
          >
            {/* The standard three-line menu icon (≡): it toggles the side drawer,
                      the same control on every screen size. */}
            <Menu aria-hidden="true" className="size-icon-md" />
          </button>
          <button
            type="button"
            onClick={onOpenPalette}
            aria-keyshortcuts={PALETTE_KEY_SHORTCUTS}
            className="flex w-full max-w-md items-center gap-2 rounded-input border border-line bg-surface px-3 py-1 text-body-sm font-semibold text-muted hover:text-ink"
          >
            <Search aria-hidden="true" className="size-icon-sm" />
            <span className="flex-1 text-left">Search</span>
            <kbd className="font-mono">{paletteKeyLabel()}</kbd>
          </button>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            className="rounded-input border border-line px-3 py-1 font-mono text-caption hover:text-accent"
          >
            {theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
          </button>
          <button
            type="button"
            onClick={onSignOut}
            aria-label="Sign out"
            className="inline-flex items-center gap-2 rounded-input border border-line px-3 py-1 text-body-sm font-semibold text-muted hover:text-ink"
          >
            <LogOut aria-hidden="true" className="size-icon-sm" />
            <span className="hidden xl:inline">Sign out</span>
          </button>
        </div>
      </header>
      <div className="relative flex min-h-0 flex-1">
        {narrow && !drawerOpen ? null : (
          <nav
            id="primary-navigation"
            aria-label="Primary"
            // The widths are design.md §3's 240 px rail and 56 px icon rail, now
            // tokens (`w-rail`, `w-rail-collapsed`, T-402) instead of a class the
            // inline style then overrode.
            className={
              narrow
                ? 'absolute inset-y-0 left-0 z-40 flex w-rail flex-col border-r border-line bg-base shadow-overlay'
                : `flex flex-col border-r border-line bg-base transition-[width] duration-panel ${
                    collapsed ? 'w-rail-collapsed' : 'w-rail'
                  }`
            }
          >
            <div className="flex h-topbar items-center px-4">
              <div className="flex items-center gap-2">
                <AegisLogo />
                {!collapsed ? <span className="text-h2">AEGIS</span> : null}
              </div>
            </div>

            {sections.map((section) => (
              <div key={section} className="mt-4">
                {!collapsed ? (
                  <p className="px-4 text-caption uppercase tracking-wide text-muted">{section}</p>
                ) : null}
                <ul>
                  {navItems
                    .filter((item) => item.section === section)
                    .map((item) => (
                      <li key={item.to}>
                        <NavLink
                          to={item.to}
                          onClick={() => {
                            // Choosing an entry closes the drawer, so the screen it opened is visible.
                            if (narrow) setDrawerOpen(false);
                          }}
                          end={item.to === '/'}
                          title={item.label}
                          className={({ isActive }) =>
                            `flex items-center gap-2 px-4 py-2 text-body ${
                              collapsed ? 'justify-center' : ''
                            } ${
                              isActive ? 'border-l-2 border-brand text-ink' : 'text-muted'
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
          {narrow ? <NarrowNotice showQueueLink /> : null}

          <main className="flex-1 p-6">{children ?? <Outlet />}</main>
          <footer className="border-t border-line px-6 py-3 text-body-sm font-semibold text-muted">
            AEGIS · Threat detection
          </footer>
        </div>
      </div>
    </div>
  );
}
