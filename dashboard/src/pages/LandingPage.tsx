import React from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, Eye, Zap, Network, Sparkles, Lock, ArrowRight } from "lucide-react";
import BrandLogo from "../components/BrandLogo";
import { BRAND_TAGLINE, BRAND_NAME } from "../constants/brand";

const LandingPage: React.FC = () => (
  <div className="min-h-screen bg-app-bg text-content-primary flex flex-col font-sans">
    <header className="h-16 border-b border-card-border bg-card-bg sticky top-0 z-20 shadow-card">
      <div className="max-w-6xl mx-auto px-6 h-full flex items-center justify-between">
        <BrandLogo size={32} />
        <div className="flex items-center gap-3">
          <Link to="/login" className="px-4 py-2 rounded-xl bg-app-void hover:bg-card-border border border-card-border text-slate-300 text-xs font-semibold transition">
            Sign In
          </Link>
          <Link
            to="/register"
            className="px-4 py-2 rounded-xl bg-accent-amber hover:bg-accent-amber-hover text-app-bg text-xs font-bold transition shadow-sm"
          >
            Start Free
          </Link>
        </div>
      </div>
    </header>

    <main className="flex-1">
      {/* Hero Section */}
      <section className="max-w-6xl mx-auto px-6 py-16 lg:py-24">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <span className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-bold bg-amber-500/10 text-accent-amber border border-amber-500/20">
              <Sparkles size={14} />
              {BRAND_NAME} — Autonomous AI Security Analyst
            </span>

            <h1 className="text-4xl lg:text-5xl font-extrabold font-display tracking-tight text-content-primary leading-tight">
              {BRAND_TAGLINE}
              <span className="block text-slate-400 text-lg font-medium mt-3 font-sans">
                You employ an analyst, you don't operate a complex dashboard.
              </span>
            </h1>

            <p className="text-content-secondary leading-relaxed max-w-xl text-sm font-sans">
              NOCTRA synthesizes security telemetry (Okta, CrowdStrike, GuardDuty, Cloudflare) into plain-English incident stories, maps affected blast-radius assets, and drafts reversible remediation actions for your 1-click approval.
            </p>

            <div className="flex flex-wrap gap-3 pt-2">
              <Link to="/register" className="px-6 py-3 rounded-xl bg-accent-amber hover:bg-accent-amber-hover text-app-bg font-bold text-xs transition shadow-sm flex items-center gap-2">
                Start with NOCTRA <ArrowRight size={14} />
              </Link>
              <Link to="/login" className="px-6 py-3 rounded-xl bg-card-bg border border-card-border text-slate-300 font-bold text-xs hover:bg-app-void transition">
                Open Analyst Console
              </Link>
            </div>

            <div className="flex items-center gap-2 text-xs text-slate-400 font-mono pt-2">
              <Lock size={14} className="text-emerald-400" />
              <span>No credit card required • Self-hosted via Docker or Kubernetes</span>
            </div>
          </div>

          {/* Right Card: Live Analyst Reasoning Demonstration */}
          <div className="bg-card-bg text-white rounded-2xl p-6 shadow-card border border-accent-amber/20 space-y-6">
            <div className="flex items-center justify-between border-b border-card-border pb-3">
              <span className="text-xs font-bold text-accent-amber font-mono uppercase tracking-wider">
                LIVE ANALYST CORE LOOP
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Active Reasoning
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {[
                { icon: Eye, label: "1. Sense Telemetry", desc: "Identity, endpoint & cloud logs" },
                { icon: ShieldCheck, label: "2. Plain-English Story", desc: "Narrative & threat rationale" },
                { icon: Zap, label: "3. Reversible Action", desc: "Drafted SOAR & undo pathway" },
                { icon: Network, label: "4. Blast Radius Graph", desc: "Affected asset entity map" },
              ].map((f) => (
                <div key={f.label} className="rounded-xl bg-app-void border border-card-border p-3.5 space-y-1">
                  <f.icon size={16} className="text-accent-amber mb-1" />
                  <p className="text-xs font-bold text-slate-200">{f.label}</p>
                  <p className="text-[11px] text-slate-400 leading-tight">{f.desc}</p>
                </div>
              ))}
            </div>

            <div className="rounded-xl bg-app-void border border-card-border p-4 font-mono text-xs space-y-1">
              <p className="text-slate-400">POST /api/v1/analyst/simulate</p>
              <p className="text-accent-amber font-bold">→ CRITICAL • credential_leak alert:T1078</p>
              <p className="text-emerald-400">→ Recommended Action: REVOKE_CREDENTIALS [Reversible]</p>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer className="border-t border-card-border bg-card-bg py-6 text-center text-xs text-slate-500 font-mono">
      © {new Date().getFullYear()} NOCTRA — Silent. Precise. Always watching.
    </footer>
  </div>
);

export default LandingPage;
