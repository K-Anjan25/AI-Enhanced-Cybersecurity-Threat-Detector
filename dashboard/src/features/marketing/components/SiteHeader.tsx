import { useEffect, useId, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { NAV_ITEMS } from '../content';

/**
 * Top bar and the only navigation: a hamburger on every screen size. The menu is a
 * full-screen overlay, closes on Escape, locks background scroll while open, and
 * returns focus to the hamburger when it closes.
 *
 * The overlay is a sibling of the sticky bar, not a child. A backdrop-filter on the
 * bar would otherwise become the containing block for the fixed overlay.
 */
export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  // Route change closes the menu.
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
    document.addEventListener('keydown', onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.getElementById(menuId)?.querySelector<HTMLAnchorElement>('a')?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, menuId]);

  return (
    <>
      <header className="sticky top-0 z-20 border-b border-line bg-base">
        <div className="mx-auto flex w-full max-w-[1200px] items-center justify-between px-6 py-3 md:px-12">
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
          <div className="flex items-center gap-6">
            <Link
              to="/sign-in"
              className="hidden text-body font-semibold text-accent no-underline hover:underline md:inline"
            >
              Sign in
            </Link>
            <button
              ref={buttonRef}
              type="button"
              aria-expanded={open}
              aria-controls={menuId}
              aria-label={open ? 'Close menu' : 'Open menu'}
              onClick={() => setOpen((value) => !value)}
              className="flex size-12 flex-col items-center justify-center gap-2 rounded-input border border-line hover:border-accent focus-visible:ring-2"
            >
              <span
                className={`marketing-bar block h-[2px] w-6 bg-ink ${open ? 'translate-y-2 rotate-45' : ''}`}
                aria-hidden="true"
              />
              <span
                className={`marketing-bar block h-[2px] w-6 bg-ink ${open ? 'opacity-0' : ''}`}
                aria-hidden="true"
              />
              <span
                className={`marketing-bar block h-[2px] w-6 bg-ink ${open ? '-translate-y-2 -rotate-45' : ''}`}
                aria-hidden="true"
              />
            </button>
          </div>
        </div>
      </header>

      <nav
        id={menuId}
        aria-label="Main"
        className={`fixed inset-0 z-30 flex-col justify-center overflow-y-auto bg-base px-6 py-16 md:px-12 ${open ? 'flex' : 'hidden'}`}
      >
        <ul className="mx-auto grid w-full max-w-[520px] list-none gap-2 p-0">
          {NAV_ITEMS.map((item, index) => {
            const current = pathname === item.to;
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  aria-current={current ? 'page' : undefined}
                  className={`flex items-baseline gap-4 rounded-card border px-4 py-3 text-display no-underline hover:border-accent hover:text-accent ${current ? 'border-line text-accent' : 'border-transparent text-ink'}`}
                >
                  <span className="font-mono text-caption text-accent" aria-hidden="true">
                    0{index + 1}
                  </span>
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
        <div className="mx-auto mt-8 w-full max-w-[520px]">
          <Link
            to="/pricing"
            className="flex w-full items-center justify-center gap-2 rounded-pill bg-accent px-6 py-3 text-caption font-semibold uppercase tracking-widest text-onAccent no-underline"
          >
            Start free trial
          </Link>
          <Link
            to="/sign-in"
            className="mt-4 block text-center text-body font-semibold text-accent no-underline hover:underline"
          >
            Sign in to the console
          </Link>
        </div>
      </nav>
    </>
  );
}
