import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, PlayCircle, CheckCircle2 } from "lucide-react";
import { TrustPill } from "../ui";

/**
 * LandingHero — Apple product-page hero, exactly as designed in the L concept:
 * centered on light-gray #F5F5F7, tiny mono overline, huge tight SF-style
 * headline with one violet-gradient phrase, one-line subhead, two pill CTAs,
 * then a large floating dark-navy product card (the analyst inbox) centered
 * with a big soft shadow.
 */

const PREVIEW_STATS = [
  { label: "Affected", value: "4 systems" },
  { label: "Confidence", value: "96%" },
  { label: "Recommends", value: "REVOKE_CREDENTIALS" },
  { label: "Reversible", value: "Yes" },
] as const;

const ProductCard: React.FC = () => (
  <div
    aria-label="Illustrative preview of the NOCTRA analyst inbox"
    className="relative mx-auto max-w-3xl animate-fade-up"
  >
    <div className="night relative overflow-hidden rounded-[2rem] border border-app-void bg-app-navy shadow-hero">
      {/* Window chrome */}
      <div className="flex items-center gap-1.5 px-5 h-11 border-b border-line-bright/40 bg-app-void/60">
        <span className="w-3 h-3 rounded-full bg-white/20" aria-hidden />
        <span className="w-3 h-3 rounded-full bg-white/20" aria-hidden />
        <span className="w-3 h-3 rounded-full bg-white/20" aria-hidden />
        <span className="ml-3 text-[10px] font-mono text-content-tertiary">NOCTRA — analyst inbox</span>
        <span className="ml-auto text-[9px] font-mono uppercase tracking-[0.2em] px-1.5 py-0.5 rounded-full border border-line-bright/40 text-content-tertiary">
          illustrative
        </span>
      </div>

      <div className="p-6 sm:p-8">
        {/* Inbox header */}
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">
              Needs your decision
            </p>
            <p className="mt-0.5 text-sm font-semibold text-content-primary">Good morning — 1 case is waiting.</p>
          </div>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border bg-severity-critical/15 text-severity-critical border-severity-critical/30">
            <span className="w-1.5 h-1.5 rounded-full bg-severity-critical" aria-hidden />
            critical
          </span>
        </div>

        {/* Case */}
        <h3 className="mt-5 text-xl sm:text-2xl font-bold font-display tracking-tight leading-snug text-balance">
          Leaked corporate credential is being used to sign in
        </h3>
        <p className="mt-2 text-sm text-content-secondary leading-relaxed max-w-xl">
          An employee credential appeared in breach evidence and is now authenticating from an
          unrecognized network. The account may be compromised.
        </p>

        {/* Stats */}
        <dl className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-4 rounded-2xl bg-app-void/40 border border-line-bright/20 p-4">
          {PREVIEW_STATS.map((s) => (
            <div key={s.label}>
              <dt className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">{s.label}</dt>
              <dd className="mt-0.5 text-sm font-bold font-mono text-content-primary">{s.value}</dd>
            </div>
          ))}
        </dl>

        {/* Decision rail */}
        <div className="mt-6 flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-content-secondary">
            <CheckCircle2 size={14} className="text-status-success" aria-hidden />
            Approve → <span className="font-mono">action recorded</span> → report generated
          </div>
          <div className="sm:ml-auto flex items-center gap-2">
            <span className="text-[11px] font-mono text-content-tertiary">record-only</span>
            <span className="inline-flex px-4 py-2 rounded-full bg-app-subtle border border-line-bright/40 text-xs font-semibold text-content-primary">
              Decline
            </span>
            <span className="inline-flex px-4 py-2 rounded-full bg-brand-gradient text-brand-ink text-xs font-semibold">
              Approve
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
);

const LandingHero: React.FC = () => (
  <section className="relative overflow-hidden bg-[#F5F5F7] text-neutral-900 pt-32 sm:pt-40 pb-20 sm:pb-28">
    {/* Soft ambient top light */}
    <div
      aria-hidden
      className="pointer-events-none absolute -top-32 left-1/2 -translate-x-1/2 h-72 w-[46rem] max-w-full rounded-full bg-brand-gradient-soft blur-3xl"
    />

    <div className="relative max-w-4xl mx-auto px-4 sm:px-6 text-center">
      <p className="text-[11px] font-mono uppercase tracking-[0.3em] text-neutral-500">
        Your autonomous security analyst
      </p>

      <h1 className="mt-5 text-[2.6rem] sm:text-6xl lg:text-7xl font-semibold tracking-[-0.03em] leading-[1.02] text-balance">
        The analyst your team{" "}
        <span className="bg-brand-gradient bg-clip-text text-transparent">doesn't have.</span>
      </h1>

      <p className="mt-5 text-base sm:text-lg text-neutral-500 leading-relaxed max-w-2xl mx-auto">
        NOCTRA watches your tools, explains every incident in plain English, and proposes one
        reversible action at a time. You approve. It records.
      </p>

      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Link
          to="/register"
          className="inline-flex items-center gap-2 px-7 py-3.5 rounded-full bg-brand-gradient text-brand-ink text-sm font-semibold hover:opacity-90 transition shadow-float"
        >
          Start free <ArrowRight size={15} aria-hidden />
        </Link>
        <a
          href="#product"
          className="inline-flex items-center gap-2 px-7 py-3.5 rounded-full bg-white text-neutral-900 text-sm font-semibold border border-black/10 hover:bg-neutral-50 transition shadow-card"
        >
          <PlayCircle size={15} className="text-violet-600" aria-hidden />
          See how it works
        </a>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
        <TrustPill>Record-only by design</TrustPill>
        <TrustPill>Append-only audit trail</TrustPill>
        <TrustPill>Self-hostable</TrustPill>
      </div>
    </div>

    {/* Floating product card */}
    <div className="relative max-w-5xl mx-auto px-4 sm:px-6 mt-16 sm:mt-20">
      <ProductCard />
    </div>
  </section>
);

export default LandingHero;
