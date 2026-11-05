import { useEffect, useId, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { NAV_ITEMS } from '../content';

/**
 * Top bar with the menu at the top-left, before the logo. The menu opens as a
 * dropdown panel directly under the bar, so the page stays visible and does not
 * need a scroll lock. It closes after a link is picked, on Escape, or on a click
 * outside it. Escape and the button return focus to the hamburger.
 */
export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const headerRef = useRef<HTMLElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  // Picking a link changes the route, which closes the menu.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onPointer = (event: MouseEvent) => {
      if (headerRef.current && !headerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onPointer);
    document.getElementById(menuId)?.querySelector<HTMLAnchorElement>('a')?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onPointer);
    };
  }, [open, menuId]);

  return (
    <header ref={headerRef} className="sticky top-0 z-20 border-b border-line bg-base">
      <div className="mx-auto flex w-full max-w-[1200px] items-center justify-between px-6 py-3 md:px-12">
        <div className="flex items-center gap-3">
          <button
            ref={buttonRef}
            type="button"
            aria-expanded={open}
            aria-controls={menuId}
            aria-label={open ? 'Close menu' : 'Open menu'}
            onClick={() => setOpen((value) => !value)}
            className="flex size-12 flex-col items-center justify-center gap-2 focus-visible:ring-2"
          >
            <span className="marketing-bar block h-[2px] w-6 bg-accent" aria-hidden="true" />
            <span className="marketing-bar block h-[2px] w-6 bg-accent" aria-hidden="true" />
            <span className="marketing-bar block h-[2px] w-6 bg-accent" aria-hidden="true" />
          </button>
          <Link
            to="/"
            className="flex items-center gap-2 text-h2 font-semibold tracking-widest text-ink no-underline"
            aria-label="AEGIS home"
          >
            <img
              src="/aegis-logo.png"
              alt=""
              width="48"
              height="48"
              className="size-12 rounded-card"
            />
            AEGIS
          </Link>
        </div>
        <Link
          to="/sign-in"
          className="hidden text-body font-semibold text-accent no-underline hover:underline md:inline"
        >
          Sign in
        </Link>
      </div>

      <nav
        id={menuId}
        aria-label="Main"
        hidden={!open}
        className="absolute inset-x-0 top-full border-b border-line bg-surface shadow-overlay"
      >
        <ul className="mx-auto grid w-full max-w-[1200px] list-none gap-1 p-4 md:px-12">
          {NAV_ITEMS.map((item) => {
            const current = pathname === item.to;
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  aria-current={current ? 'page' : undefined}
                  className={`block rounded-card border px-4 py-3 text-body font-semibold no-underline hover:border-accent hover:text-accent ${current ? 'border-line text-accent' : 'border-transparent text-ink'}`}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
          <li className="mt-2 flex flex-wrap gap-4 px-4 pt-2">
            <Link
              to="/sign-in"
              className="text-body font-semibold text-accent no-underline hover:underline"
            >
              Sign in to the console
            </Link>
            <Link
              to="/pricing"
              className="text-body font-semibold text-accent no-underline hover:underline"
            >
              Start free trial
            </Link>
          </li>
        </ul>
      </nav>
    </header>
  );
}
