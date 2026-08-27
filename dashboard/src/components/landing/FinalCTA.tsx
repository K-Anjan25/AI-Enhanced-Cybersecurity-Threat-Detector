import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, FileText, GitBranch, ShieldCheck, ScrollText, Workflow } from "lucide-react";
import { SectionLabel } from "../ui";
import BrandLogo from "../BrandLogo";
import { BRAND_TAGLINE_SECONDARY } from "../../constants/brand";

/**
 * FinalCTA — the closing conversion panel (WordPress landing pattern):
 * a brand-gradient band with one clear next step, over a quiet footer with
 * real links (product routes + repository docs).
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
    <section id="why" className="scroll-mt-24 max-w-6xl mx-auto px-4 sm:px-6 py-20 sm:py-24">
      <div className="relative overflow-hidden rounded-3xl night bg-app-navy border border-app-void shadow-hero px-6 py-14 sm:px-12 text-center">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 h-64 w-[40rem] max-w-full rounded-full bg-brand-gradient-soft blur-3xl"
        />
        <div className="relative">
          <SectionLabel className="justify-center">Employ your analyst</SectionLabel>
          <h2 className="mt-4 text-display-xl font-bold font-display tracking-tight text-balance max-w-2xl mx-auto">
            The night shift is covered. The decisions are yours.
          </h2>
          <p className="mt-4 text-base text-content-secondary leading-relaxed max-w-xl mx-auto">
            Self-hosted via Docker Compose or Kubernetes. Telemetry stays on your infrastructure.
            Your data never trains our models.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/register"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-brand-gradient text-brand-ink font-semibold hover:opacity-90 transition shadow-float"
            >
              Start free <ArrowRight size={16} aria-hidden />
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-app-subtle border border-line-subtle text-content-primary font-semibold hover:bg-app-surface-raised transition"
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

    <footer className="border-t border-line-subtle bg-app-surface">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-14 grid grid-cols-2 md:grid-cols-4 gap-10">
        <div className="col-span-2 md:col-span-1">
          <BrandLogo size={26} />
          <p className="mt-3 text-xs text-content-tertiary leading-relaxed max-w-[16rem]">
            {BRAND_TAGLINE_SECONDARY} — an autonomous security analyst for small teams. Calm,
            precise, accountable.
          </p>
        </div>
        {FOOTER_COLS.map((col) => (
          <nav key={col.title} aria-label={col.title}>
            <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">
              {col.title}
            </p>
            <ul className="mt-3 space-y-2">
              {col.links.map((l) => (
                <li key={l.label}>
                  {l.to.startsWith("http") ? (
                    <a
                      href={l.to}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-content-secondary hover:text-accent-primary transition"
                    >
                      {l.label}
                    </a>
                  ) : (
                    <Link
                      to={l.to}
                      className="text-xs text-content-secondary hover:text-accent-primary transition"
                    >
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
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <p className="text-[11px] text-content-tertiary">
            © {new Date().getFullYear()} NOCTRA — See less. Know more.
          </p>
          <p className="text-[11px] text-content-tertiary inline-flex items-center gap-1.5">
            <FileText size={11} aria-hidden /> Actions are recorded, never executed.
          </p>
        </div>
      </div>
    </footer>
  </>
);

export default FinalCTA;
