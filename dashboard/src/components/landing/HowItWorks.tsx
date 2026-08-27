import React from "react";
import { Link } from "react-router-dom";
import { SectionLabel } from "../ui";

/**
 * HowItWorks — the analyst loop rendered as a numbered timeline (WordPress
 * "steps" pattern). 8 steps, each a real stage of the product loop, no
 * invented numbers.
 */
const STEPS = [
  { n: "01", title: "Sense", body: "Telemetry from Okta, CrowdStrike, GuardDuty and Cloudflare becomes one stream of observable events." },
  { n: "02", title: "Reason", body: "ML + heuristics flag anomalies; the analyst engine builds a real blast-radius graph." },
  { n: "03", title: "Explain", body: "NOCTRA writes the case in plain English — what happened, why it matters, what's affected." },
  { n: "04", title: "Propose", body: "One reversible action per case, with an explicit undo path and stated confidence." },
  { n: "05", title: "Approve", body: "You approve, decline, or reverse. The decision is yours; NOCTRA never acts alone." },
  { n: "06", title: "Record", body: "Approved actions are recorded through SOAR — nothing is ever executed against your systems." },
  { n: "07", title: "Audit", body: "Every transition is appended to the audit trail: who decided, when, and what was recorded." },
  { n: "08", title: "Report", body: "A downloadable markdown report captures the outcome, blast radius and undo instructions." },
] as const;

const HowItWorks: React.FC = () => (
  <section id="how-it-works" className="scroll-mt-24 border-y border-line-subtle bg-app-surface">
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20 sm:py-24">
      <div className="max-w-2xl">
        <SectionLabel>How it works</SectionLabel>
        <h2 className="mt-4 text-display-xl font-bold font-display tracking-tight text-balance">
          The whole product is this loop
        </h2>
        <p className="mt-4 text-base text-content-secondary leading-relaxed">
          Sense → reason → explain → propose → approve → record → audit → report. Everything else
          is progressive disclosure.
        </p>
      </div>

      <ol className="mt-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-10">
        {STEPS.map((s) => (
          <li key={s.n} className="relative pl-7">
            <span
              aria-hidden
              className="absolute left-0 top-1 w-4 h-4 rounded-full border-2 border-accent-primary/40 flex items-center justify-center"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-accent-primary" />
            </span>
            <p className="text-[11px] font-mono text-accent-secondary tracking-[0.2em]">{s.n}</p>
            <h3 className="mt-1.5 text-sm font-bold font-sans tracking-tight text-content-primary">
              {s.title}
            </h3>
            <p className="mt-1.5 text-[13px] text-content-secondary leading-relaxed">{s.body}</p>
          </li>
        ))}
      </ol>

      <div className="mt-12 flex flex-col sm:flex-row sm:items-center gap-4 rounded-2xl border border-line-subtle bg-app-bg p-6">
        <p className="text-sm text-content-secondary leading-relaxed">
          <span className="font-semibold text-content-primary">See it end to end in about a minute.</span>{" "}
          Sign in, run a simulated incident, and review your first real case — a credential leak
          with a live blast-radius graph.
        </p>
        <Link
          to="/register"
          className="sm:ml-auto shrink-0 inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-brand-gradient text-brand-ink text-sm font-semibold hover:opacity-90 transition"
        >
          Run the demo
        </Link>
      </div>
    </div>
  </section>
);

export default HowItWorks;
