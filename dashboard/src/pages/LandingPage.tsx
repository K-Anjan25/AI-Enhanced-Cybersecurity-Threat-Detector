import React from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, Eye, Zap, Network } from "lucide-react";
import BrandLogo from "../components/BrandLogo";
import { BRAND_TAGLINE, BRAND_NAME } from "../constants/brand";

const LandingPage: React.FC = () => (
  <div className="min-h-screen bg-app-bg text-content-primary flex flex-col">
    <header className="h-16 border-b border-line-subtle bg-white sticky top-0 z-20 shadow-card">
      <div className="max-w-6xl mx-auto px-6 h-full flex items-center justify-between">
        <BrandLogo size={32} />
        <div className="flex items-center gap-3">
          <Link to="/login" className="px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-800 text-sm font-medium transition">
            Sign in
          </Link>
          <Link
            to="/register"
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold shadow-cobalt hover:bg-blue-700 transition"
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
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
              <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse" />
              {BRAND_NAME} — Autonomous AI Security Analyst
            </span>
            <h1 className="text-4xl lg:text-5xl font-extrabold font-display tracking-tight text-slate-900 leading-tight">
              {BRAND_TAGLINE}
              <span className="block text-slate-500 text-xl font-medium mt-3">Employ an AI security analyst; don't operate a complex dashboard.</span>
            </h1>
            <p className="text-slate-600 leading-relaxed max-w-xl text-base">
              {BRAND_NAME} synthesizes multi-source log streams (Okta, CrowdStrike, GuardDuty, Cloudflare) into plain-English incident stories, maps affected blast-radius entities, and drafts reversible remediation actions for your team's one-click approval.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link to="/register" className="px-6 py-3 rounded-xl bg-blue-600 text-white font-bold shadow-cobalt hover:bg-blue-700 transition">
                Start with AXIOM AI
              </Link>
              <Link to="/login" className="px-6 py-3 rounded-xl bg-white border border-slate-200 text-slate-800 font-semibold hover:bg-slate-50 transition">
                Open Console
              </Link>
            </div>
            <p className="text-xs text-slate-500">No credit card required • Self-hosted via Docker Compose or Kubernetes</p>
          </div>

          <div className="bg-[#0e1320] text-white rounded-2xl p-6 shadow-navy border border-slate-800">
            <div className="grid grid-cols-2 gap-4">
              {[
                { icon: Eye, label: "Multi-Source Sense", desc: "Identity / endpoint / cloud logs" },
                { icon: ShieldCheck, label: "Plain-English Story", desc: "Narrative & threat rationale" },
                { icon: Zap, label: "Reversible Action", desc: "Drafted SOAR & undo pathway" },
                { icon: Network, label: "Blast Radius Graph", desc: "Affected asset entity map" },
              ].map((f) => (
                <div key={f.label} className="rounded-xl bg-slate-900/80 border border-slate-800 p-4">
                  <f.icon size={18} className="text-blue-400 mb-2" />
                  <p className="text-sm font-semibold text-white">{f.label}</p>
                  <p className="text-xs text-slate-400 mt-0.5">{f.desc}</p>
                </div>
              ))}
            </div>
            <div className="mt-6 rounded-xl bg-slate-950 border border-slate-800 p-4 font-mono text-xs">
              <p className="text-slate-400">POST /api/v1/analyst/simulate</p>
              <p className="text-blue-400 mt-1">→ CRITICAL — credential_leak alert:T1078 action:REVOKE_CREDENTIALS</p>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer className="border-t border-line-subtle bg-white py-6 text-center text-xs text-slate-500">
      © {new Date().getFullYear()} AXIOM AI — Self-evident threat reasoning. Instant containment.
    </footer>
  </div>
);

export default LandingPage;
