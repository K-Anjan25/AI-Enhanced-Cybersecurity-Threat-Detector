import { ArrowUpRight, Fingerprint } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { AegisLogo } from '../../components/brand/AegisLogo';
import { ThreeField } from './ThreeField';

const NAV: ReadonlyArray<{ label: string; href: string }> = [
  { label: 'Features', href: '#features' },
  { label: 'Pipeline', href: '#pipeline' },
  { label: 'Security', href: '#security' },
];

/**
 * Keeps `--scroll` on the page root in step with the scroll position, so CSS depth
 * layers can move at their own speeds. Updates run once per frame.
 */
function useScrollDepth(rootRef: React.RefObject<HTMLElement>) {
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;
    let frame = 0;
    const update = () => {
      frame = 0;
      root.style.setProperty('--scroll', String(window.scrollY / 100));
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [rootRef]);
}

/** The public front page, shown at `/` to anyone without a session. */
export function LandingPage() {
  const rootRef = useRef<HTMLElement>(null);
  useScrollDepth(rootRef);

  return (
    <main
      ref={rootRef}
      className="landing-stage landing-backdrop flex min-h-screen flex-col overflow-x-hidden text-ink"
    >
      <header className="sticky top-0 z-20 bg-base/70 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1200px] items-center justify-between px-6 py-4 md:px-12">
          <span className="flex items-center gap-2 text-h2 font-semibold">
            <AegisLogo />
            AEGIS
          </span>
          <nav aria-label="Primary" className="hidden gap-8 md:flex">
            {NAV.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="text-caption uppercase tracking-widest"
              >
                {item.label}
              </a>
            ))}
          </nav>
          <Link
            to="/sign-in"
            className="rounded-full border border-line px-6 py-2 text-caption font-semibold uppercase tracking-widest hover:bg-surface"
          >
            Get protected
          </Link>
        </div>
      </header>

      {/* Hero: the 3D field fills the section; text sits on three depth layers. */}
      <section className="relative isolate flex min-h-[calc(100svh-4.5rem)] items-center overflow-hidden">
        <ThreeField />
        <div className="relative mx-auto grid w-full max-w-[1200px] items-center gap-10 px-6 py-16 md:grid-cols-12 md:px-12">
          <div
            className="landing-layer z-10 flex flex-col gap-8 md:col-span-4"
            style={{ '--depth-y': '-10px', '--depth-z': '60px' } as React.CSSProperties}
          >
            <p className="max-w-xs text-body text-muted">
              Protect your data, AI models, and network traffic with real-time threat detection,
              anomaly scoring, and automated triage.
            </p>
            <Link
              to="/sign-in"
              className="inline-flex w-max items-center rounded-full bg-accent px-8 py-3 text-caption font-semibold uppercase tracking-widest text-onAccent"
            >
              Protect your data
            </Link>
          </div>

          <h1
            className="landing-layer z-10 text-hero md:col-span-8 md:col-start-5 md:text-right"
            style={{ '--depth-y': '-22px', '--depth-z': '-40px' } as React.CSSProperties}
          >
            Detect to Protect
            <br />
            <span className="md:pl-16">AI-Powered</span>
            <br />
            Networks
          </h1>
        </div>
      </section>

      {/* Content sections follow the hero directly, so no spacer is left behind. */}
      <section className="relative mx-auto grid w-full max-w-[1200px] gap-6 px-6 pb-16 md:grid-cols-12 md:px-12">
        <article
          id="features"
          className="landing-layer landing-card z-10 flex flex-col items-center gap-4 rounded-card bg-surface p-6 text-center md:col-span-4"
          style={{ '--depth-y': '-6px', '--depth-z': '20px' } as React.CSSProperties}
        >
          <p className="text-caption font-semibold uppercase tracking-widest">AI-Powered</p>
          <Fingerprint aria-hidden="true" className="my-4 size-16 text-accent" />
          <p className="text-caption text-muted">Scanning securely...</p>
        </article>

        <article
          id="security"
          className="landing-layer landing-card z-10 flex flex-col gap-6 rounded-card bg-surface p-6 md:col-span-4"
          style={{ '--depth-y': '-12px', '--depth-z': '40px' } as React.CSSProperties}
        >
          <h2 className="text-h1 text-center font-semibold uppercase leading-tight">Detection</h2>
          <p className="text-center text-body-sm text-muted">
            Scan flows, logs, and captures with AI anomaly scoring.
          </p>
          <Link
            to="/sign-in"
            className="mt-auto text-center text-caption font-semibold uppercase tracking-widest underline underline-offset-4"
          >
            Start detecting
          </Link>
        </article>

        <article
          id="pipeline"
          className="landing-layer landing-card z-10 flex items-end justify-between gap-6 rounded-card bg-surface p-6 md:col-span-4"
          style={{ '--depth-y': '-18px', '--depth-z': '60px' } as React.CSSProperties}
        >
          <div className="flex flex-col gap-2">
            <p className="text-h2 font-semibold">Monitoring</p>
            <p className="text-stat font-semibold tabular">24/7</p>
          </div>
          <Link to="/sign-in" aria-label="Open the dashboard">
            <ArrowUpRight aria-hidden="true" className="size-icon-md" />
          </Link>
        </article>
      </section>

      <footer className="relative z-10 mt-auto flex items-center justify-between border-t border-line px-6 py-4 text-caption text-muted">
        <span>AEGIS · Threat detection</span>
        <Link to="/sign-in" className="underline underline-offset-4 hover:text-ink">
          Sign in
        </Link>
      </footer>
    </main>
  );
}
