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
import { SectionLabel } from "../ui";

/**
 * FeatureGrid — the WordPress/SaaS bento grid: six real product capabilities,
 * each with a lucide mark, plain copy, and a deep-dive link. Every feature is
 * shipped and reachable at the linked route.
 */
const FEATURES = [
  {
    icon: MessageSquareText,
    title: "Plain-English briefs",
    body: "Every case answers what happened, why it matters, and what's affected — with stated confidence, never alarm.",
    to: "/feed",
    cta: "Open a case",
  },
  {
    icon: Share2,
    title: "Blast-radius graph",
    body: "NOCTRA maps the real entity graph behind an incident: accounts, hosts, IPs and the connections between them.",
    to: "/entities",
    cta: "Explore the graph",
  },
  {
    icon: Undo2,
    title: "One reversible action",
    body: "Each case proposes a single action with an undo path. You approve or decline; the action is recorded, never executed.",
    to: "/actions",
    cta: "View actions log",
  },
  {
    icon: ShieldCheck,
    title: "Record-only SOAR",
    body: "Automation drafts and records, humans decide. Every recommendation is traceable to a rule and a case.",
    to: "/soar",
    cta: "See SOAR",
  },
  {
    icon: ScrollText,
    title: "Append-only audit trail",
    body: "Every decision, chat question and state change is written to an append-only log you can inspect.",
    to: "/admin/system-logs",
    cta: "Read the audit",
  },
  {
    icon: FileText,
    title: "Case reports",
    body: "Approved cases generate a markdown report: summary, blast radius, decision, action and how to undo it.",
    to: "/reports",
    cta: "Browse reports",
  },
] as const;

const FeatureGrid: React.FC = () => (
  <section id="product" className="scroll-mt-24 max-w-6xl mx-auto px-4 sm:px-6 py-20 sm:py-24">
    <div className="max-w-2xl">
      <SectionLabel>The product</SectionLabel>
      <h2 className="mt-4 text-display-xl font-bold font-display tracking-tight text-balance">
        An analyst, not another dashboard
      </h2>
      <p className="mt-4 text-base text-content-secondary leading-relaxed">
        NOCTRA is the employee your security team doesn't have. It works through the night,
        brings you one case at a time, and writes everything down.
      </p>
    </div>

    <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {FEATURES.map((f) => {
        const Icon = f.icon;
        return (
          <article
            key={f.title}
            className="group rounded-2xl border border-line-subtle bg-app-surface p-6 hover:border-accent-primary/40 hover:shadow-raised hover:-translate-y-0.5 transition"
          >
            <div className="w-10 h-10 rounded-xl bg-brand-gradient-soft border border-accent-primary/20 flex items-center justify-center">
              <Icon size={18} className="text-accent-secondary" aria-hidden />
            </div>
            <h3 className="mt-4 text-base font-bold font-sans tracking-tight text-content-primary">
              {f.title}
            </h3>
            <p className="mt-2 text-sm text-content-secondary leading-relaxed">{f.body}</p>
            <Link
              to={f.to}
              className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-accent-secondary hover:text-accent-primary transition"
            >
              {f.cta}
              <ArrowUpRight size={13} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" aria-hidden />
            </Link>
          </article>
        );
      })}
    </div>
  </section>
);

export default FeatureGrid;
