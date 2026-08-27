import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, PlayCircle, CheckCircle2 } from "lucide-react";
import { SectionLabel, TrustPill, cn } from "../ui";

/**
 * LandingHero — WordPress-grade marketing hero: statement → mechanism →
 * trust, with the actual product preview built in CSS (a real NOCTRA case
 * card, labeled illustrative) instead of stock art.
 */

const HERO_STATS: ReadonlyArray<{
  label: string;
  value: string;
  mono: boolean;
  accent?: boolean;
}> = [
  { label: "Affected", value: "4 systems", mono: true },
  { label: "Confidence", value: "96%", mono: true },
  { label: "Recommends", value: "REVOKE_CREDENTIALS", mono: true, accent: true },
  { label: "Reversible", value: "Yes", mono: true },
];

const ProductPreview: React.FC = () => (
  <div
    aria-label="Illustrative preview of the NOCTRA analyst inbox"
    className="relative animate-fade-up"
  >
    {/* Soft brand halo — flat gradient, no glow, per brand avoid-list. */}
    <div
      aria-hidden
      className="absolute -inset-6 rounded-[2rem] bg-brand-gradient-soft blur-2xl"
    />

    <div className="relative night bg-app-navy text-content-primary rounded-2xl border border-app-void shadow-hero overflow-hidden">
      {/* Window chrome */}
      <div className="flex items-center gap-2 px-4 h-9 border-b border-line-subtle bg-app-void/60">
        <span className="w-2.5 h-2.5 rounded-full bg-line-bright" aria-hidden />
        <span className="w-2.5 h-2.5 rounded-full bg-line-bright" aria-hidden />
        <span className="w-2.5 h-2.5 rounded-full bg-line-bright" aria-hidden />
        <span className="ml-3 text-[10px] font-mono text-content-tertiary">
          NOCTRA — analyst inbox
        </span>
        <span className="ml-auto text-[9px] font-mono uppercase tracking-[0.2em] px-1.5 py-0.5 rounded border border-line-subtle text-content-tertiary">
          illustrative
        </span>
      </div>

      {/* Inbox header */}
      <div className="px-5 pt-5 pb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">
            Needs your decision
          </p>
          <p className="mt-0.5 text-sm font-semibold text-content-primary">
            Good morning — 1 case is waiting.
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border bg-severity-critical/15 text-severity-critical border-severity-critical/30">
          <span className="w-1.5 h-1.5 rounded-full bg-severity-critical" aria-hidden />
          critical
        </span>
      </div>

      {/* Case headline */}
      <div className="px-5 pb-5">
        <h3 className="text-lg font-bold font-display leading-snug text-balance">
          Leaked corporate credential is being used to sign in
        </h3>
        <p className="mt-2 text-sm text-content-secondary leading-relaxed">
          An employee credential appeared in breach evidence and is now authenticating from an
          unrecognized network. The account may be compromised.
        </p>
      </div>

      {/* Stats */}
      <dl className="px-5 pb-5 grid grid-cols-2 sm:grid-cols-4 gap-4">
        {HERO_STATS.map((s) => (
          <div key={s.label}>
            <dt className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">
              {s.label}
            </dt>
            <dd
              className={cn(
                "mt-0.5 text-sm font-bold font-mono",
                s.accent ? "text-accent-secondary" : "text-content-primary"
              )}
            >
              {s.value}
            </dd>
          </div>
        ))}
      </dl>

      {/* Decision rail — the product's core gesture */}
      <div className="px-5 py-4 border-t border-line-subtle bg-app-void/40 flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex items-center gap-2 text-xs text-content-secondary">
          <CheckCircle2 size={14} className="text-status-success" aria-hidden />
          Approve → <span className="font-mono">action recorded</span> → report generated
        </div>
        <div className="sm:ml-auto flex items-center gap-2">
          <span className="text-[11px] font-mono text-content-tertiary">record-only</span>
          <span className="inline-flex px-3 py-1.5 rounded-lg bg-app-subtle border border-line-subtle text-xs font-semibold text-content-primary">
            Decline
          </span>
          <span className="inline-flex px-3 py-1.5 rounded-lg bg-brand-gradient text-brand-ink text-xs font-semibold">
            Approve
          </span>
        </div>
      </div>
    </div>
  </div>
);

const LandingHero: React.FC = () => (
  <section className="relative overflow-hidden">
    {/* Quiet top light — flat radial, no neon. */}
    <div
      aria-hidden
      className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 h-96 w-[52rem] max-w-full rounded-full bg-brand-gradient-soft blur-3xl"
    />

    <div className="relative max-w-6xl mx-auto px-4 sm:px-6 pt-16 sm:pt-24 pb-16 grid grid-cols-1 lg:grid-cols-[1.05fr_0.95fr] gap-12 lg:gap-10 items-center">
      <div className="animate-fade-up">
        <SectionLabel className="gap-2.5">
          <span className="w-1.5 h-1.5 rounded-full bg-accent-primary animate-pulse" aria-hidden />
          Your autonomous security analyst
        </SectionLabel>

        <h1 className="mt-5 text-display-2xl font-bold font-display tracking-tight text-balance">
          See less.{" "}
          <span className="bg-brand-gradient bg-clip-text text-transparent">Know more.</span>
        </h1>

        <p className="mt-6 text-base sm:text-lg text-content-secondary leading-relaxed max-w-xl">
          NOCTRA watches your Okta, CrowdStrike, GuardDuty and Cloudflare telemetry continuously,
          explains every incident in plain English, maps what's affected, and proposes{" "}
          <span className="font-semibold text-content-primary">one reversible action</span> at a
          time. You approve. It records — it never executes against your systems.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link
            to="/register"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-brand-gradient text-brand-ink font-semibold hover:opacity-90 transition shadow-float"
          >
            Start free <ArrowRight size={16} aria-hidden />
          </Link>
          <a
            href="#how-it-works"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-app-surface border border-line-subtle text-content-primary font-semibold hover:bg-app-surface-raised transition"
          >
            <PlayCircle size={16} className="text-accent-secondary" aria-hidden />
            See how it works
          </a>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-2">
          <TrustPill icon="shield">Record-only by design</TrustPill>
          <TrustPill icon="lock">Self-hostable</TrustPill>
          <TrustPill icon="check">Append-only audit trail</TrustPill>
        </div>
      </div>

      <div className="animate-fade-up [animation-delay:120ms]">
        <ProductPreview />
      </div>
    </div>
  </section>
);

export default LandingHero;
