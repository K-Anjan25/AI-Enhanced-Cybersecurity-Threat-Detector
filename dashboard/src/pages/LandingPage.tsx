import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import BrandLogo from "../components/BrandLogo";
import { BRAND_TAGLINE, BRAND_NAME } from "../constants/brand";

/**
 * Landing — Intelligence Infrastructure.
 * Editorial enterprise structure: overline → statement → mechanism → proof.
 * The example case is clearly labeled illustrative; no fabricated metrics,
 * no live-data claims. Day workspace hero; one night canvas panel carries
 * the product's voice — duality demonstrated, not described.
 */

const LOOP = [
  "Sense",
  "Reason",
  "Explain",
  "Blast radius",
  "Propose",
  "Approve",
  "Record",
  "Report",
];

const PILLARS = [
  {
    n: "01",
    title: "Sense",
    body: "Telemetry from Okta, CrowdStrike, GuardDuty and Cloudflare becomes one stream of observable events.",
  },
  {
    n: "02",
    title: "Reason",
    body: "Every incident is analyzed and explained in plain English — what happened, why it matters, what is affected — with stated confidence, never presented as confirmed fact.",
  },
  {
    n: "03",
    title: "Decide",
    body: "NOCTRA proposes one reversible action per case. You approve or decline. It records the decision and writes the report.",
  },
];

const LandingPage: React.FC = () => (
  <div className="min-h-screen bg-app-bg text-content-primary flex flex-col">
    <header className="h-16 border-b border-line-subtle bg-app-surface sticky top-0 z-20">
      <div className="max-w-5xl mx-auto px-6 h-full flex items-center justify-between">
        <BrandLogo size={30} />
        <div className="flex items-center gap-3">
          <Link
            to="/login"
            className="px-4 py-2 rounded-lg bg-app-subtle hover:bg-app-surface-raised border border-line-subtle text-content-primary text-sm font-medium transition"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="px-4 py-2 rounded-lg bg-accent-primary text-brand-ink text-sm font-semibold hover:opacity-90 transition"
          >
            Start free
          </Link>
        </div>
      </div>
    </header>

    <main className="flex-1">
      {/* Statement */}
      <section className="max-w-5xl mx-auto px-6 pt-20 pb-14">
        <p className="text-[11px] font-mono uppercase tracking-[0.3em] text-content-tertiary">
          Intelligence infrastructure
        </p>
        <h1 className="mt-4 text-4xl lg:text-[3.4rem] font-bold font-display tracking-tight leading-[1.05] max-w-3xl">
          {BRAND_TAGLINE}
        </h1>
        <p className="mt-5 text-base text-content-secondary leading-relaxed max-w-2xl">
          {BRAND_NAME} is intelligence infrastructure for small security teams. Telemetry
          goes in; decisions come out. It watches continuously, explains every incident
          in plain English, maps what is affected, and proposes one reversible action at
          a time. You approve. It records — it never executes against your systems.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <Link
            to="/register"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-accent-primary text-brand-ink font-semibold hover:opacity-90 transition"
          >
            Start free <ArrowRight size={16} aria-hidden />
          </Link>
          <Link
            to="/login"
            className="px-6 py-3 rounded-xl bg-app-surface border border-line-subtle text-content-primary font-semibold hover:bg-app-surface-raised transition"
          >
            Open console
          </Link>
        </div>
        <p className="mt-4 text-xs text-content-tertiary">
          Self-hosted via Docker Compose or Kubernetes. Your telemetry stays yours.
        </p>
      </section>

      {/* Mechanism — the loop as content */}
      <section className="border-y border-line-subtle bg-app-surface">
        <div className="max-w-5xl mx-auto px-6 py-8">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-3">
            {LOOP.map((step, i) => (
              <React.Fragment key={step}>
                <span className="text-[11px] font-mono uppercase tracking-[0.18em] text-content-secondary">
                  {step}
                </span>
                {i < LOOP.length - 1 && (
                  <span className="text-content-tertiary" aria-hidden>
                    →
                  </span>
                )}
              </React.Fragment>
            ))}
          </div>
          <p className="mt-3 text-xs text-content-tertiary">
            The whole product is this loop. Everything else is progressive disclosure.
          </p>
        </div>
      </section>

      {/* Proof — an example case, on the night canvas (illustrative). */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <h2 className="text-2xl font-bold font-sans tracking-tight">One case, end to end</h2>
          <span className="text-[10px] font-mono uppercase tracking-[0.2em] px-2 py-1 rounded border border-line-subtle bg-app-subtle text-content-tertiary">
            Example — illustrative
          </span>
        </div>

        <div className="night mt-6 bg-app-navy text-content-primary rounded-2xl border border-app-void shadow-navy p-6 lg:p-8">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">
              Needs your decision
            </p>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-medium border bg-severity-critical/15 text-severity-critical border-severity-critical/30">
              <span className="w-1.5 h-1.5 rounded-full bg-severity-critical" />
              critical
            </span>
          </div>

          <h3 className="mt-3 text-xl font-bold font-display leading-snug">
            Leaked corporate credential is being used to sign in
          </h3>
          <p className="mt-2 text-sm text-content-secondary leading-relaxed max-w-2xl">
            An employee credential appeared in breach evidence and is now authenticating
            from an unrecognized network. The account may be compromised.
          </p>

          <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Affected</p>
              <p className="text-sm font-bold font-mono mt-0.5">4 systems</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Confidence</p>
              <p className="text-sm font-bold font-mono mt-0.5">96%</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Recommends</p>
              <p className="text-sm font-bold font-mono text-accent-secondary mt-0.5">REVOKE_CREDENTIALS</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Reversible</p>
              <p className="text-sm font-bold font-mono mt-0.5">Yes</p>
            </div>
          </div>

          <div className="mt-6 pt-5 border-t border-line-bright flex flex-col sm:flex-row sm:items-center gap-4">
            <div className="flex items-center gap-2 text-xs text-content-secondary">
              <CheckCircle2 size={14} className="text-status-success" aria-hidden />
              Approve → <span className="font-mono">action recorded</span> → report generated
            </div>
            <span className="sm:ml-auto text-[11px] text-content-tertiary font-mono">
              record-only — nothing is executed
            </span>
          </div>
        </div>
      </section>

      {/* Pillars — editorial numbered sections */}
      <section className="border-t border-line-subtle bg-app-surface">
        <div className="max-w-5xl mx-auto px-6 py-16 grid grid-cols-1 md:grid-cols-3 gap-10">
          {PILLARS.map((p) => (
            <article key={p.n}>
              <p className="text-[11px] font-mono text-accent-secondary tracking-[0.2em]">{p.n}</p>
              <h3 className="mt-2 text-lg font-bold font-sans tracking-tight">{p.title}</h3>
              <p className="mt-2 text-sm text-content-secondary leading-relaxed">{p.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* Trust strip */}
      <section className="border-t border-line-subtle">
        <div className="max-w-5xl mx-auto px-6 py-10 flex flex-col sm:flex-row sm:items-center gap-4">
          <p className="text-sm text-content-secondary leading-relaxed">
            <span className="font-semibold text-content-primary">Record-only by design.</span>{" "}
            NOCTRA records actions — it never executes them. Every decision is reversible,
            every step audited, every outcome reported.
          </p>
          <Link
            to="/register"
            className="sm:ml-auto shrink-0 inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-accent-primary text-brand-ink text-sm font-semibold hover:opacity-90 transition"
          >
            Employ your analyst <ArrowRight size={15} aria-hidden />
          </Link>
        </div>
      </section>
    </main>

    <footer className="border-t border-line-subtle bg-app-surface py-6">
      <div className="max-w-5xl mx-auto px-6 flex items-center justify-between gap-4">
        <BrandLogo size={22} withWordmark={false} />
        <p className="text-xs text-content-tertiary">
          © {new Date().getFullYear()} {BRAND_NAME} — See less. Know more.
        </p>
      </div>
    </footer>
  </div>
);

export default LandingPage;
