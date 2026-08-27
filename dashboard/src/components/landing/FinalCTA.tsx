import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, FileText, GitBranch, ShieldCheck, ScrollText, Workflow } from "lucide-react";
import BrandLogo from "../BrandLogo";
import { BRAND_TAGLINE } from "../../constants/brand";

/**
 * FinalCTA — Apple-style dark closing band: centered statement on navy,
 * one gradient CTA, quiet multi-column footer with real links.
 */

const FOOTER_COLS = [
  {
    title: "Product",
    links: [
      { label: "Analyst inbox", to: "/" },
      { label: "Cases", to: "/feed" },
      { label: "Actions log", to: "/actions" },
      { label: "Reports", to: "/reports" },
    ],
  },
  {
    title: "Investigate",
    links: [
      { label: "Alerts", to: "/alerts" },
      { label: "Entities & graph", to: "/entities" },
      { label: "Analytics", to: "/analytics" },
      { label: "SOAR", to: "/soar" },
    ],
  },
  {
    title: "Trust",
    links: [
      { label: "Audit trail", to: "/admin/system-logs" },
      { label: "Reputation intel", to: "/admin/reputation" },
      { label: "Engine settings", to: "/admin/engine-settings" },
      { label: "GitHub repository", to: "https://github.com/K-Anjan25/AI-Enhanced-Cybersecurity-Threat-Detector" },
    ],
  },
] as const;

const FinalCTA: React.FC = () => (
  <>
    <section id="why" className="scroll-mt-24 max-w-5xl mx-auto px-4 sm:px-6 py-24 sm:py-28">
      <div className="relative overflow-hidden rounded-[2.5rem] night bg-app-navy border border-app-void shadow-hero px-6 py-16 sm:px-16 text-center">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 h-64 w-[38rem] max-w-full rounded-full bg-brand-gradient-soft blur-3xl"
        />
        <div className="relative">
          <p className="text-[11px] font-mono uppercase tracking-[0.3em] text-content-tertiary">
            Employ your analyst
          </p>
          <h2 className="mt-4 text-4xl sm:text-5xl font-semibold tracking-[-0.02em] text-white text-balance max-w-2xl mx-auto">
            The night shift is covered. The decisions are yours.
          </h2>
          <p className="mt-4 text-base text-content-secondary leading-relaxed max-w-xl mx-auto">
            Self-hosted via Docker Compose or Kubernetes. Telemetry stays on your infrastructure.
            Your data never trains our models.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/register"
              className="inline-flex items-center gap-2 px-7 py-3.5 rounded-full bg-brand-gradient text-brand-ink font-semibold hover:opacity-90 transition shadow-float"
            >
              Start free <ArrowRight size={15} aria-hidden />
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center gap-2 px-7 py-3.5 rounded-full bg-app-surface text-content-primary font-semibold hover:bg-app-surface-raised transition shadow-card border border-line-subtle"
            >
              Open console
            </Link>
          </div>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 text-[11px] font-mono text-content-tertiary">
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck size={12} aria-hidden /> record-only
            </span>
            <span className="inline-flex items-center gap-1.5">
              <ScrollText size={12} aria-hidden /> append-only audit
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Workflow size={12} aria-hidden /> REST or Kafka
            </span>
            <span className="inline-flex items-center gap-1.5">
              <GitBranch size={12} aria-hidden /> open repo
            </span>
          </div>
        </div>
      </div>
    </section>

    <footer className="bg-app-surface border-t border-line-subtle">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-14 grid grid-cols-2 md:grid-cols-4 gap-10">
        <div className="col-span-2 md:col-span-1">
          <BrandLogo size={24} />
          <p className="mt-3 text-xs text-content-secondary leading-relaxed max-w-[16rem]">
            {BRAND_TAGLINE} Calm, precise, accountable — the analyst a small team employs.
          </p>
        </div>
        {FOOTER_COLS.map((col) => (
          <nav key={col.title} aria-label={col.title}>
            <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">{col.title}</p>
            <ul className="mt-3 space-y-2">
              {col.links.map((l) => (
                <li key={l.label}>
                  {l.to.startsWith("http") ? (
                    <a
                      href={l.to}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-content-secondary hover:text-accent-secondary transition"
                    >
                      {l.label}
                    </a>
                  ) : (
                    <Link to={l.to} className="text-xs text-content-secondary hover:text-accent-secondary transition">
                      {l.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="border-t border-line-subtle">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <p className="text-[11px] text-content-tertiary">© {new Date().getFullYear()} NOCTRA</p>
          <p className="text-[11px] text-content-tertiary inline-flex items-center gap-1.5">
            <FileText size={11} aria-hidden /> Actions are recorded, never executed.
          </p>
        </div>
      </div>
    </footer>
  </>
);

export default FinalCTA;
