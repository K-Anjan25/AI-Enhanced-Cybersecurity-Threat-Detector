import React from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, Eye, Zap, Network } from "lucide-react";
import BrandLogo from "../components/BrandLogo";
import { BRAND_TAGLINE } from "../constants/brand";

const LandingPage: React.FC = () => (
  <div className="min-h-screen bg-app-bg text-content-primary flex flex-col">
    <header className="h-16 border-b border-line-subtle bg-app-surface/80 backdrop-blur sticky top-0 z-20">
      <div className="max-w-6xl mx-auto px-6 h-full flex items-center justify-between">
        <BrandLogo size={30} />
        <div className="flex items-center gap-3">
          <Link to="/login" className="px-4 py-2 rounded-lg bg-app-subtle hover:bg-line-bright border border-line-subtle text-sm transition">
            Sign in
          </Link>
          <Link
            to="/register"
            className="px-4 py-2 rounded-lg bg-gradient-to-r from-accent-primary to-brand-violet text-white text-sm font-semibold shadow-accent-glow hover:opacity-90 transition"
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
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-accent-primary/10 text-accent-primary border border-accent-primary/20">
              <span className="w-2 h-2 rounded-full bg-accent-primary animate-pulse" />
              NOCTRA — Threat Ops Platform
            </span>
            <h1 className="text-4xl lg:text-5xl font-bold tracking-tight leading-tight">
              {BRAND_TAGLINE}
              <span className="block text-content-secondary text-xl font-normal mt-3">The AI analyst that never blinks.</span>
            </h1>
            <p className="text-content-secondary leading-relaxed max-w-xl">
              Detect across logs, email and network. Every verdict is explainable. Every response is orchestratable. Built for the SOC night shift — dark-native, WCAG AA, and ready for 10k alerts.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link to="/register" className="px-6 py-3 rounded-xl bg-gradient-to-r from-accent-primary to-brand-violet text-white font-semibold shadow-accent-glow hover:opacity-90 transition">
                Create analyst account
              </Link>
              <Link to="/login" className="px-6 py-3 rounded-xl bg-app-surface border border-line-subtle hover:bg-app-surface-raised transition">
                Open console
              </Link>
            </div>
            <p className="text-xs text-content-tertiary">No credit card • Self-hosted via Docker Compose or K8s</p>
          </div>

          <div className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-raised">
            <div className="grid grid-cols-2 gap-4">
              {[
                { icon: Eye, label: "Detect", desc: "Log / email / network ML" },
                { icon: ShieldCheck, label: "Explain", desc: "Evidence per verdict" },
                { icon: Zap, label: "Respond", desc: "SOAR playbooks + auto" },
                { icon: Network, label: "Connect", desc: "Entity graph + MITRE" },
              ].map((f) => (
                <div key={f.label} className="rounded-xl bg-app-bg border border-line-subtle p-4">
                  <f.icon size={18} className="text-accent-primary mb-2" />
                  <p className="text-sm font-semibold">{f.label}</p>
                  <p className="text-xs text-content-tertiary mt-0.5">{f.desc}</p>
                </div>
              ))}
            </div>
            <div className="mt-6 rounded-xl bg-app-bg border border-line-subtle p-4 font-mono text-xs">
              <p className="text-content-tertiary">POST /api/v1/analyze</p>
              <p className="text-accent-primary mt-1">→ CRITICAL — mitre:T1059 + intel:malicious</p>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer className="border-t border-line-subtle py-6 text-center text-xs text-content-tertiary">© {new Date().getFullYear()} NOCTRA — Built for the night shift.</footer>
  </div>
);

export default LandingPage;
