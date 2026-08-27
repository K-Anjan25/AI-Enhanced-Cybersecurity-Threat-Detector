import React from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, Eye, Zap, Network, Moon } from "lucide-react";
import BrandLogo from "../components/BrandLogo";
import { BRAND_TAGLINE, BRAND_TAGLINE_SECONDARY, BRAND_NAME } from "../constants/brand";

const LandingPage: React.FC = () => (
  <div className="min-h-screen bg-app-bg text-content-primary flex flex-col">
    <header className="h-16 border-b border-line-subtle bg-app-surface sticky top-0 z-20 shadow-card">
      <div className="max-w-6xl mx-auto px-6 h-full flex items-center justify-between">
        <BrandLogo size={32} />
        <div className="flex items-center gap-3">
          <Link
            to="/login"
            className="px-4 py-2 rounded-lg bg-app-subtle hover:bg-app-surface-raised border border-line-subtle text-content-primary text-sm font-medium transition"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="px-4 py-2 rounded-lg bg-accent-primary text-app-bg text-sm font-semibold shadow-lumen hover:bg-accent-secondary transition"
          >
            Start free
          </Link>
        </div>
      </div>
    </header>

    <main className="flex-1">
      <section className="max-w-6xl mx-auto px-6 py-16 lg:py-24">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold bg-accent-primary/10 text-accent-glow border border-accent-primary/30">
              <Moon size={12} aria-hidden />
              {BRAND_NAME} — {BRAND_TAGLINE}
            </span>
            <h1 className="text-4xl lg:text-5xl font-extrabold font-display tracking-tight text-content-primary leading-tight">
              {BRAND_TAGLINE}
              <span className="block text-content-secondary text-xl font-medium mt-3">
                Employ an AI security analyst; don't operate a complex dashboard.
              </span>
            </h1>
            <p className="text-content-secondary leading-relaxed max-w-xl text-base">
              {BRAND_NAME} synthesizes multi-source log streams (Okta, CrowdStrike, GuardDuty,
              Cloudflare) into plain-English incident stories, maps affected blast-radius entities,
              and drafts reversible remediation actions for your one-click approval. It records
              every decision — it never executes against your systems.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                to="/register"
                className="px-6 py-3 rounded-xl bg-accent-primary text-app-bg font-bold shadow-lumen hover:bg-accent-secondary transition"
              >
                Start with {BRAND_NAME}
              </Link>
              <Link
                to="/login"
                className="px-6 py-3 rounded-xl bg-app-surface border border-line-subtle text-content-primary font-semibold hover:bg-app-surface-raised transition"
              >
                Open Console
              </Link>
            </div>
            <p className="text-xs text-content-tertiary">Self-hosted via Docker Compose or Kubernetes</p>
          </div>

          {/* Night canvas — what the analyst does, at a glance. */}
          <div className="bg-app-navy text-content-primary rounded-2xl p-6 shadow-navy border border-line-bright">
            <div className="grid grid-cols-2 gap-4">
              {[
                { icon: Eye, label: "Multi-Source Sense", desc: "Identity / endpoint / cloud logs" },
                { icon: ShieldCheck, label: "Plain-English Story", desc: "Narrative & threat rationale" },
                { icon: Zap, label: "Reversible Action", desc: "Drafted SOAR & undo pathway" },
                { icon: Network, label: "Blast Radius Graph", desc: "Affected asset entity map" },
              ].map((f) => (
                <div key={f.label} className="rounded-xl bg-app-void/80 border border-line-bright p-4">
                  <f.icon size={18} className="text-accent-glow mb-2" />
                  <p className="text-sm font-semibold text-content-primary">{f.label}</p>
                  <p className="text-xs text-content-tertiary mt-0.5">{f.desc}</p>
                </div>
              ))}
            </div>
            <div className="mt-6 rounded-xl bg-app-void border border-line-bright p-4 font-mono text-xs">
              <p className="text-content-tertiary">POST /api/v1/analyst/simulate</p>
              <p className="text-accent-glow mt-1">
                → CRITICAL — credential_leak alert:T1078 action:REVOKE_CREDENTIALS
              </p>
              <p className="text-content-tertiary mt-1">→ awaiting your decision…</p>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer className="border-t border-line-subtle bg-app-surface py-6 text-center text-xs text-content-tertiary">
      © {new Date().getFullYear()} {BRAND_NAME} — {BRAND_TAGLINE_SECONDARY} Every decision
      recorded, every action reversible.
    </footer>
  </div>
);

export default LandingPage;
