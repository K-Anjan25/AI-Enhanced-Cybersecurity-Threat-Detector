import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { CalendarCheck } from 'lucide-react';

/** Scroll distance (px) after which the sticky call-to-action appears. */
const SHOW_AFTER_PX = 640;

/**
 * Floating call-to-action that appears once the visitor has scrolled past the hero.
 * It is not rendered at all while hidden, so it is never in the tab order or the
 * accessibility tree while off-screen.
 */
export function StickyCta() {
  const [visible, setVisible] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > SHOW_AFTER_PX);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  if (!visible || pathname === '/contact') return null;

  return (
    <Link
      to="/contact"
      className="fixed bottom-4 right-4 z-20 inline-flex items-center gap-2 rounded-pill bg-accent px-6 py-3 text-caption font-semibold uppercase tracking-widest text-onAccent shadow-overlay no-underline max-md:inset-x-4 max-md:justify-center"
    >
      <CalendarCheck aria-hidden="true" className="size-icon-md" />
      Book a demo
    </Link>
  );
}
