import { ArrowUpRight, Fingerprint } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AegisLogo } from '../../components/brand/AegisLogo';

/**
 * Hero art. The centre portrait is `dashboard/public/landing-hero.png`, already
 * coloured in the blue halftone treatment. If the file is missing the
 * halftone field stands alone.
 */
const HERO_ART = '/landing-hero.png';

const NAV: ReadonlyArray<{ label: string; href: string }> = [
  { label: 'Features', href: '#features' },
  { label: 'Pipeline', href: '#pipeline' },
  { label: 'Security', href: '#security' },
];

/** The public front page, shown at `/` to anyone without a session. */
export function LandingPage() {
  const [artLoaded, setArtLoaded] = useState(true);

  return (
    <main className="landing-backdrop relative flex min-h-screen flex-col overflow-hidden text-ink">
      <header className="relative z-10 mx-auto flex w-full max-w-[1200px] items-center justify-between px-6 py-4 md:px-12">
        <span className="flex items-center gap-2 text-h2 font-semibold">
          <AegisLogo />
          AEGIS
        </span>
        <nav aria-label="Primary" className="hidden gap-8 md:flex">
          {NAV.map((item) => (
            <a key={item.label} href={item.href} className="text-caption uppercase tracking-widest">
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
      </header>

      <div className="relative flex-1 border-t border-dashed border-line">
        <section className="relative mx-auto grid max-w-[1200px] gap-8 px-6 py-12 md:min-h-[640px] md:grid-cols-12 md:px-12">
          <div className="z-10 flex flex-col gap-8 md:col-span-4 md:pt-4">
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

          <h1 className="z-10 text-hero md:col-span-8 md:col-start-5 md:text-right">
            Detect to Protect
            <br />
            <span className="md:pl-16">AI-Powered</span>
            <br />
            Networks
          </h1>

          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 top-16 bottom-0 hidden md:block"
          >
            <div className="absolute inset-y-0 left-1/2 w-[46%] -translate-x-1/2">
              <div className="landing-halftone absolute inset-0" />
              {artLoaded ? (
                <img
                  src={HERO_ART}
                  alt=""
                  onError={() => setArtLoaded(false)}
                  className="absolute inset-0 size-full object-contain"
                />
              ) : null}
            </div>
          </div>

          <article
            id="features"
            className="z-10 w-full max-w-[200px] self-end rounded-card bg-surface p-6 text-center md:col-span-3 md:col-start-1 md:row-start-3 md:mt-16"
          >
            <p className="text-caption font-semibold uppercase tracking-widest">AI-Powered</p>
            <Fingerprint aria-hidden="true" className="mx-auto my-6 size-16 text-accent" />
            <p className="text-caption text-muted">Scanning securely...</p>
          </article>

          <article
            id="security"
            className="z-10 flex flex-col gap-6 rounded-card bg-surface p-6 md:col-span-3 md:col-start-10 md:row-span-2 md:row-start-2 md:mt-16"
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
            className="z-10 flex items-end justify-between gap-6 rounded-card bg-surface p-6 md:col-span-6 md:col-start-1 md:row-start-4"
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
      </div>
    </main>
  );
}
