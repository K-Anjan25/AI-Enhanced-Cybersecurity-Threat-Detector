import React from "react";
import { Link } from "react-router-dom";
import {
  MessageSquareText,
  Share2,
  Undo2,
  ShieldCheck,
  ScrollText,
  FileText,
  ArrowUpRight,
} from "lucide-react";
import { Term } from "../ui";

/**
 * FeatureGrid — Apple bento: 6 real capabilities on white cards with large
 * radii and soft shadows, dotted-underline terminology on the first jargon
 * words (dogfooded plain-English glosses).
 */
const FEATURES = [
  {
    icon: MessageSquareText,
    title: "Plain-English briefs",
    body: (
      <>
        Every <Term>case</Term> answers what happened, why it matters, and what's affected — with
        stated <Term>confidence</Term>, never alarm.
      </>
    ),
    to: "/feed",
    cta: "Open a case",
  },
  {
    icon: Share2,
    title: "Blast-radius graph",
    body: (
      <>
        NOCTRA maps the real <Term>blast radius</Term> behind an incident: accounts, hosts, IPs
        and the connections between them.
      </>
    ),
    to: "/entities",
    cta: "Explore the graph",
  },
  {
    icon: Undo2,
    title: "One reversible action",
    body: (
      <>
        Each case proposes a single <Term>reversible</Term> action with an{" "}
        <Term>undo</Term> path. You approve or decline; the action is{" "}
        <Term>record-only</Term>.
      </>
    ),
    to: "/actions",
    cta: "View actions log",
  },
  {
    icon: ShieldCheck,
    title: "Record-only SOAR",
    body: (
      <>
        <Term>SOAR</Term> drafts and records; humans decide. Every recommendation is traceable
        to a rule and a case.
      </>
    ),
    to: "/soar",
    cta: "See SOAR",
  },
  {
    icon: ScrollText,
    title: "Append-only audit trail",
    body: (
      <>
        Every <Term>decision</Term>, chat question and state change is written to an append-only
        log you can inspect.
      </>
    ),
    to: "/admin/system-logs",
    cta: "Read the audit",
  },
  {
    icon: FileText,
    title: "Case reports",
    body: (
      <>
        Approved cases generate a markdown report: summary, <Term>blast radius</Term>, decision,
        action and how to <Term>undo</Term> it.
      </>
    ),
    to: "/reports",
    cta: "Browse reports",
  },
] as const;

const FeatureGrid: React.FC = () => (
  <section id="product" className="scroll-mt-24 max-w-5xl mx-auto px-4 sm:px-6 py-24 sm:py-28">
    <div className="max-w-2xl mx-auto text-center">
      <p className="text-[11px] font-mono uppercase tracking-[0.3em] text-content-tertiary">The product</p>
      <h2 className="mt-4 text-4xl sm:text-5xl font-semibold tracking-[-0.02em] text-content-primary text-balance">
        An analyst, not another dashboard
      </h2>
      <p className="mt-4 text-base text-content-secondary leading-relaxed">
        NOCTRA is the employee your security team doesn't have. It works through the night,
        brings you one case at a time, and writes everything down.
      </p>
    </div>

    <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {FEATURES.map((f) => {
        const Icon = f.icon;
        return (
          <article
            key={f.title}
            className="group rounded-[1.75rem] border border-line-subtle bg-app-surface p-7 shadow-card hover:shadow-float hover:-translate-y-0.5 transition"
          >
            <div className="w-11 h-11 rounded-2xl bg-brand-gradient-soft border border-accent-primary/20 flex items-center justify-center">
              <Icon size={19} className="text-accent-secondary" aria-hidden />
            </div>
            <h3 className="mt-5 text-lg font-semibold tracking-tight text-content-primary">{f.title}</h3>
            <p className="mt-2 text-sm text-content-secondary leading-relaxed">{f.body}</p>
            <Link
              to={f.to}
              className="mt-4 inline-flex items-center gap-1 text-[13px] font-semibold text-accent-secondary hover:text-accent-primary transition"
            >
              {f.cta}
              <ArrowUpRight size={14} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" aria-hidden />
            </Link>
          </article>
        );
      })}
    </div>
  </section>
);

export default FeatureGrid;
