import React from "react";
import { Link } from "react-router-dom";
import { Term } from "../ui";

/**
 * HowItWorks — the analyst loop as a clean 4×2 grid of numbered steps
 * (Apple spec-sheet style), with plain-English terminology on first jargon.
 */
const STEPS = [
  { n: "01", title: "Sense", body: <>Telemetry from Okta, CrowdStrike, GuardDuty and Cloudflare becomes one stream of observable events.</> },
  { n: "02", title: "Reason", body: <>ML and heuristics flag anomalies; the analyst engine builds a real <Term>blast radius</Term> graph.</> },
  { n: "03", title: "Explain", body: <>NOCTRA writes the <Term>case</Term> in plain English — what happened, why it matters, what's affected.</> },
  { n: "04", title: "Propose", body: <>One <Term>reversible</Term> action per case, with an explicit <Term>undo</Term> path and stated <Term>confidence</Term>.</> },
  { n: "05", title: "Approve", body: <>You approve, decline, or reverse. The <Term>decision</Term> is yours; NOCTRA never acts alone.</> },
  { n: "06", title: "Record", body: <>Approved actions are <Term>record-only</Term> — nothing is ever executed against your systems.</> },
  { n: "07", title: "Audit", body: <>Every transition is appended to the audit trail: who decided, when, and what was recorded.</> },
  { n: "08", title: "Report", body: <>A downloadable markdown report captures the outcome, blast radius and undo instructions.</> },
] as const;

const HowItWorks: React.FC = () => (
  <section id="how-it-works" className="scroll-mt-24 bg-app-surface border-y border-line-subtle">
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-24 sm:py-28">
      <div className="max-w-2xl mx-auto text-center">
        <p className="text-[11px] font-mono uppercase tracking-[0.3em] text-content-tertiary">How it works</p>
        <h2 className="mt-4 text-4xl sm:text-5xl font-semibold tracking-[-0.02em] text-content-primary text-balance">
          The whole product is this loop
        </h2>
        <p className="mt-4 text-base text-content-secondary leading-relaxed">
          Sense → reason → explain → propose → approve → record → audit → report. Everything else
          is progressive disclosure.
        </p>
      </div>

      <ol className="mt-14 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-8 gap-y-10">
        {STEPS.map((s) => (
          <li key={s.n} className="relative">
            <p className="text-[11px] font-mono text-accent-secondary tracking-[0.2em]">{s.n}</p>
            <h3 className="mt-2 text-base font-semibold tracking-tight text-content-primary">{s.title}</h3>
            <p className="mt-1.5 text-[13px] text-content-secondary leading-relaxed">{s.body}</p>
          </li>
        ))}
      </ol>

      <div className="mt-16 flex flex-col sm:flex-row sm:items-center gap-4 rounded-[1.75rem] border border-line-subtle bg-app-bg p-7">
        <p className="text-sm text-content-secondary leading-relaxed">
          <span className="font-semibold text-content-primary">See it end to end in about a minute.</span>{" "}
          Sign in, run a simulated incident, and review your first real case — a credential leak
          with a live blast-radius graph.
        </p>
        <Link
          to="/register"
          className="sm:ml-auto shrink-0 inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-brand-gradient text-brand-ink text-sm font-semibold hover:opacity-90 transition"
        >
          Run the demo
        </Link>
      </div>
    </div>
  </section>
);

export default HowItWorks;
