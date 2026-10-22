import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowRight, BadgeCheck, Lock, Server, UserCheck } from 'lucide-react';
import { MarketingLayout } from '../marketing/MarketingLayout';
import { Accordion } from '../marketing/components/Accordion';
import { CountUp } from '../marketing/components/CountUp';
import { NewsletterForm } from '../marketing/components/NewsletterForm';
import { Reveal } from '../marketing/components/Reveal';
import { SplitFeature } from '../marketing/components/Shared';
import {
  ARCHITECTURE_STEPS,
  HOME_FAQ,
  HOME_SECTIONS,
  PIPELINE_STEPS,
  STATS,
} from '../marketing/content';
import { useScrollDepth } from '../marketing/hooks';
import { ThreeField } from './ThreeField';

const TRUST: ReadonlyArray<{ label: string; icon: typeof Server }> = [
  { label: 'Deploy inside your network', icon: Server },
  { label: 'Scoped API keys', icon: Lock },
  { label: 'Append-only audit trail', icon: BadgeCheck },
  { label: 'Single sign-on (OIDC)', icon: UserCheck },
];

/** Sample rows for the hero card. They are illustrative, and the card says so. */
const SAMPLE_ALERTS: ReadonlyArray<{
  severity: 'high' | 'medium' | 'low';
  title: string;
  meta: string;
  age: string;
}> = [
  {
    severity: 'high',
    title: 'Beaconing to a rare external host',
    meta: 'flow window 0142 · 50 records',
    age: '2 min',
  },
  {
    severity: 'medium',
    title: 'Burst of failed admin logins',
    meta: 'auth logs · grouped with 7 events',
    age: '9 min',
  },
  {
    severity: 'low',
    title: 'Unusual DNS query volume',
    meta: 'resolver logs · baseline drift',
    age: '21 min',
  },
];

const SEVERITY_FILL: Record<'high' | 'medium' | 'low', string> = {
  high: 'bg-severity-high',
  medium: 'bg-severity-medium',
  low: 'bg-severity-low',
};

/**
 * The public home page, shown at `/` to anyone without a session.
 *
 * The hero sits on three depth layers: the 3D field, a grid and the copy. The scroll
 * position is written to `--scroll` on the hero, so each layer moves at its own speed.
 */
export function LandingPage() {
  const heroRef = useRef<HTMLElement>(null);
  useScrollDepth(heroRef);
  const [scoreReady, setScoreReady] = useState(false);
  useEffect(() => {
    // Let the bar animate from zero once the card has been painted.
    const frame = requestAnimationFrame(() => setScoreReady(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <MarketingLayout
      title="AEGIS | AI-Enhanced Threat Detection for Security Teams"
      description="AEGIS scores network flows and system logs with machine-learning models, then turns anomalies into prioritised alerts your analysts can triage in minutes."
    >
      {/* Hero: the 3D field fills the section; text and cards sit on depth layers above it. */}
      <section
        ref={heroRef}
        aria-labelledby="hero-title"
        className="landing-stage relative isolate flex min-h-[calc(100svh-4.5rem)] items-center overflow-hidden"
      >
        <ThreeField />
        <div
          aria-hidden="true"
          className="marketing-grid pointer-events-none absolute inset-0 -z-10"
        />
        {/*
          Scrim between the animated field and the copy, so every glyph sits on a surface
          that passes AA (D-091). It is decorative and uses the scoped base token.
        */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(ellipse 62% 58% at 50% 50%, color-mix(in srgb, var(--color-bg-base) 90%, transparent) 0%, color-mix(in srgb, var(--color-bg-base) 74%, transparent) 62%, transparent 100%)',
          }}
        />

        <div className="relative mx-auto grid w-full max-w-[1200px] items-center gap-12 px-6 py-16 md:grid-cols-12 md:px-12">
          <div
            className="landing-layer z-10 flex flex-col gap-6 md:col-span-7"
            style={{ '--depth-y': '-10px', '--depth-z': '60px' } as React.CSSProperties}
          >
            <p className="m-0 font-mono text-caption uppercase tracking-widest text-accent">
              Machine-learning threat detection
            </p>
            <h1 id="hero-title" className="text-display md:text-hero">
              See the attack <span className="text-accent">before</span> it becomes an incident.
            </h1>
            <p className="m-0 max-w-[60ch] text-body text-muted md:text-h2 md:font-normal">
              AEGIS watches your network flows and system logs, scores them with machine-learning
              models, and turns the anomalies it finds into prioritised alerts your analysts can act
              on in minutes. Your data stays inside your own infrastructure.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                to="/pricing"
                className="inline-flex items-center gap-2 rounded-pill bg-accent px-6 py-3 text-caption font-semibold uppercase tracking-widest text-onAccent no-underline focus-visible:ring-2"
              >
                Start free
                <ArrowRight aria-hidden="true" className="size-icon-sm" />
              </Link>
              <Link
                to="/features"
                className="inline-flex items-center gap-2 rounded-pill border border-accent px-6 py-3 text-caption font-semibold uppercase tracking-widest text-accent no-underline hover:bg-surface focus-visible:ring-2"
              >
                See how it works
              </Link>
            </div>
          </div>

          <div
            className="landing-layer relative md:col-span-5"
            style={{ '--depth-y': '-22px', '--depth-z': '-40px' } as React.CSSProperties}
          >
            <div className="rounded-card border border-line bg-surface p-6 shadow-overlay">
              <div className="mb-3 flex items-center justify-between font-mono text-caption text-muted">
                <span>ALERT QUEUE</span>
                <span>sample data</span>
              </div>
              <ul className="m-0 grid list-none gap-0 p-0">
                {SAMPLE_ALERTS.map((alert) => (
                  <li
                    key={alert.title}
                    className="grid grid-cols-[auto_1fr_auto] items-center gap-3 border-t border-line py-3"
                  >
                    <span
                      className={`rounded-pill px-3 py-1 font-mono text-caption font-semibold uppercase text-onSeverity ${SEVERITY_FILL[alert.severity]}`}
                    >
                      {alert.severity}
                    </span>
                    <div>
                      <p className="m-0 text-body font-semibold text-ink">{alert.title}</p>
                      <p className="m-0 font-mono text-caption text-muted">{alert.meta}</p>
                    </div>
                    <span className="font-mono text-caption text-muted">{alert.age}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="relative -mt-8 ml-auto mr-4 w-[14rem] rounded-card border border-accent bg-surface p-4 shadow-overlay">
              <p className="m-0 font-mono text-caption text-muted">ANOMALY SCORE</p>
              <p className="m-0 font-mono text-stat text-accent tabular-nums">0.87</p>
              <div className="mt-2 h-1 overflow-hidden rounded-pill bg-base" aria-hidden="true">
                <div
                  className="h-full bg-accent transition-[width] duration-panel ease-out"
                  style={{ width: scoreReady ? '87%' : '0%' }}
                />
              </div>
              <p className="sr-only">Sample anomaly score of 0.87, illustrative only.</p>
            </div>
          </div>
        </div>
      </section>

      <section aria-label="Key assurances" className="border-y border-line bg-surface">
        <ul className="mx-auto grid w-full max-w-[1200px] list-none grid-cols-1 gap-0 px-6 py-0 md:grid-cols-4 md:px-12">
          {TRUST.map((item) => (
            <li
              key={item.label}
              className="flex items-center gap-3 py-4 text-body font-semibold text-ink md:px-4"
            >
              <item.icon aria-hidden="true" className="size-icon-md shrink-0 text-accent" />
              {item.label}
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="how-title"
        className="mx-auto w-full max-w-[1200px] px-6 py-16 md:px-12 md:py-[6rem]"
      >
        <Reveal>
          <div className="mx-auto mb-16 max-w-[680px] text-center">
            <p className="m-0 font-mono text-caption uppercase tracking-widest text-accent">
              How AEGIS works
            </p>
            <h2 id="how-title" className="mt-3 text-display">
              From raw traffic to a verdict your team can defend
            </h2>
            <p className="mt-3 text-body text-muted">
              Three stages, each one visible and auditable.
            </p>
          </div>
        </Reveal>
        <div className="grid gap-16">
          {HOME_SECTIONS.map((section, index) => (
            <SplitFeature key={section.eyebrow} section={section} reverse={index % 2 === 1} />
          ))}
        </div>
      </section>

      <section
        aria-labelledby="stats-title"
        className="border-y border-line bg-surface py-16 md:py-[6rem]"
      >
        <div className="mx-auto w-full max-w-[1200px] px-6 md:px-12">
          <Reveal>
            <p className="m-0 font-mono text-caption uppercase tracking-widest text-accent">
              Limits you can check
            </p>
            <h2 id="stats-title" className="mt-3 text-display">
              Defaults that are documented, not marketed
            </h2>
          </Reveal>
          <div className="mt-12 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {STATS.map((stat, index) => (
              <Reveal key={stat.label} delayMs={index * 80}>
                <div className="h-full rounded-card border border-line bg-base p-6">
                  <p className="m-0 font-mono text-stat text-accent tabular-nums">
                    <CountUp to={stat.to} suffix={stat.suffix} />
                  </p>
                  <p className="mb-0 mt-3 text-body text-muted">{stat.label}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section
        aria-labelledby="pipeline-title"
        className="mx-auto w-full max-w-[1200px] px-6 py-16 md:px-12 md:py-[6rem]"
      >
        <Reveal>
          <p className="m-0 font-mono text-caption uppercase tracking-widest text-accent">
            Getting started
          </p>
          <h2 id="pipeline-title" className="mt-3 text-display">
            Live in a week, not a quarter
          </h2>
        </Reveal>
        <ol className="mt-12 grid list-none gap-4 p-0 md:grid-cols-2 lg:grid-cols-4">
          {PIPELINE_STEPS.map(([title, body], index) => (
            <Reveal key={title} delayMs={index * 80} className="h-full">
              <li className="h-full rounded-card border-t-2 border-accent bg-surface p-6">
                <span className="font-mono text-caption text-accent">0{index + 1}</span>
                <h3 className="mt-2 text-h2 font-semibold text-ink">{title}</h3>
                <p className="mb-0 mt-2 text-body-sm text-muted">{body}</p>
              </li>
            </Reveal>
          ))}
        </ol>
      </section>

      <section
        aria-labelledby="architecture-title"
        className="mx-auto w-full max-w-[1200px] px-6 pb-16 md:px-12 md:pb-[6rem]"
      >
        <Reveal>
          <h2 id="architecture-title" className="text-display">
            From capture to case, in four stages
          </h2>
        </Reveal>
        <ol className="mt-8 grid list-none gap-4 p-0 md:grid-cols-2 lg:grid-cols-4">
          {ARCHITECTURE_STEPS.map(([title, body], index) => (
            <Reveal key={title} delayMs={index * 80} className="h-full">
              <li className="flex h-full gap-3 rounded-card border border-line bg-surface p-6">
                <Activity aria-hidden="true" className="mt-1 size-icon-sm shrink-0 text-accent" />
                <div>
                  <h3 className="m-0 text-h2 font-semibold text-ink">{title}</h3>
                  <p className="mb-0 mt-2 text-body-sm text-muted">{body}</p>
                </div>
              </li>
            </Reveal>
          ))}
        </ol>
      </section>

      <section
        aria-labelledby="faq-title"
        className="mx-auto w-full max-w-[860px] px-6 py-16 md:px-12 md:py-[6rem]"
      >
        <Reveal>
          <div className="mb-12 text-center">
            <p className="m-0 font-mono text-caption uppercase tracking-widest text-accent">FAQ</p>
            <h2 id="faq-title" className="mt-3 text-display">
              Questions security teams ask us
            </h2>
          </div>
        </Reveal>
        <Accordion items={HOME_FAQ} />
      </section>

      <section
        aria-labelledby="band-title"
        className="mx-auto w-full max-w-[1200px] px-6 pb-16 md:px-12 md:pb-[6rem]"
      >
        <Reveal>
          <div className="grid gap-8 rounded-card border border-accent bg-surface p-8 md:grid-cols-2 md:items-center md:p-12">
            <div>
              <p className="m-0 font-mono text-caption uppercase tracking-widest text-accent">
                Security briefing
              </p>
              <h2 id="band-title" className="mt-3 text-display">
                Detection research, delivered monthly.
              </h2>
              <p className="mb-0 mt-3 text-body text-muted">
                Model updates, new detection families and practical tuning notes from our team.
              </p>
            </div>
            <NewsletterForm variant="band" />
          </div>
        </Reveal>
      </section>
    </MarketingLayout>
  );
}
