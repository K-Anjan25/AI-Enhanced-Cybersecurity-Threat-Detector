import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Sparkles,
  AlertTriangle,
  Server,
  User as UserIcon,
  Globe,
  AppWindow,
  CheckCircle2,
  XCircle,
  ShieldCheck,
  RefreshCw,
  ArrowRight,
  ShieldAlert,
} from "lucide-react";
import { Button } from "../components/ui";
import AnalystApi from "../api/analystApi";
import type { Brief, Connector } from "../types/analyst";

const BriefPage: React.FC = () => {
  const navigate = useNavigate();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [selectedScenario, setSelectedScenario] = useState("credential_leak");

  const username = localStorage.getItem("username") || "Anjan";

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [briefData, connData] = await Promise.all([
        AnalystApi.fetchBrief(),
        AnalystApi.fetchConnectors().catch(() => []),
      ]);
      setBrief(briefData);
      setConnectors(connData);
    } catch (err: any) {
      setError(err?.detail || "Failed to load brief data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSimulate = async () => {
    setSimulating(true);
    setError(null);
    try {
      const created = await AnalystApi.simulate(selectedScenario);
      navigate(`/case/${created.id}`);
    } catch (err: any) {
      setError(err?.detail || "Could not simulate an incident");
      setSimulating(false);
    }
  };

  const handleSyncConnector = async (id: string) => {
    setSyncingId(id);
    try {
      await AnalystApi.syncConnector(id);
      setConnectors((prev) =>
        prev.map((c) => (c.id === id ? { ...c, last_sync: "Just now" } : c))
      );
    } catch (err: any) {
      setError(err?.detail || "Connector sync failed");
    } finally {
      setSyncingId(null);
    }
  };

  const pendingCases = brief?.top_cases ?? [];
  const latestCase = pendingCases[0];

  return (
    <div className="space-y-6 animate-fade-in bg-app-bg min-h-screen -m-6 p-6 sm:p-8">
      
      {/* Executive Analyst Greeting Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-card-bg p-6 rounded-2xl border border-card-border shadow-card">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles size={20} className="text-accent-amber" />
            <h1 className="text-xl font-bold font-display text-content-primary">
              Good morning, {username}
            </h1>
          </div>
          <p className="text-xs text-content-secondary mt-1.5 leading-relaxed font-sans">
            NOCTRA investigated <span className="font-bold text-accent-amber">24 security events</span> overnight.{" "}
            <span className="text-slate-400">• 21 resolved automatically • 2 dismissed • </span>
            <span className="font-bold text-red-400">1 requires your decision</span>
          </p>
        </div>

        {/* Incident Simulator Controller */}
        <div className="flex items-center gap-2 bg-app-void p-2 rounded-xl border border-card-border">
          <select
            value={selectedScenario}
            onChange={(e) => setSelectedScenario(e.target.value)}
            disabled={simulating}
            className="bg-card-bg border border-card-border text-xs text-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:border-accent-amber font-mono"
          >
            <option value="credential_leak">Credential Leak (T1078)</option>
            <option value="phishing_outbreak">Phishing Outbreak (T1566)</option>
            <option value="data_exfiltration">Data Exfiltration (T1048)</option>
            <option value="compromised_api_key">Compromised API Key (T1098)</option>
          </select>
          <Button
            variant="primary"
            onClick={handleSimulate}
            disabled={simulating}
            className="bg-accent-amber hover:bg-accent-amber-hover text-app-bg font-bold text-xs px-4 py-2 rounded-lg shrink-0"
          >
            <Sparkles size={14} className="mr-1.5" />
            {simulating ? "Simulating…" : "Inject Scenario"}
          </Button>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-sm text-red-400 font-medium">
          {error}
        </div>
      )}

      {/* Main Action Required Work Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Span: Action Required Case Banner */}
        <div className="lg:col-span-8 bg-card-bg rounded-2xl border border-accent-amber/30 p-6 shadow-card space-y-5">
          <div className="flex items-center justify-between border-b border-card-border pb-4">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/10 text-accent-amber border border-amber-500/30 uppercase tracking-wider">
              <ShieldAlert size={14} /> Action Required By You
            </span>
            <span className="text-xs font-mono text-slate-400">
              Confidence: {latestCase?.analysis?.confidence ? Math.round(latestCase.analysis.confidence * 100) : 96}%
            </span>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30 uppercase">
                {latestCase?.priority || "CRITICAL"}
              </span>
              <h2 className="text-lg font-bold text-content-primary font-display">
                {latestCase?.analysis?.headline || latestCase?.title || "Case #104 — Leaked Corporate Credential in Use"}
              </h2>
            </div>

            <p className="text-xs text-content-secondary leading-relaxed font-normal">
              {latestCase?.analysis?.what_happened ||
                latestCase?.description ||
                "Employee credentials 'jdoe@acme.com' were leaked in an external breach and used from 203.0.113.66 to access internal finance portal."}
            </p>
          </div>

          {/* Affected Blast Radius Assets Chips */}
          <div className="space-y-2 pt-2 border-t border-card-border">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Potential Blast Radius Impact
            </p>
            <div className="flex flex-wrap gap-2">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-mono bg-app-void text-slate-300 border border-card-border">
                <Server size={12} className="text-accent-amber" /> Finance Database
              </span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-mono bg-app-void text-slate-300 border border-card-border">
                <UserIcon size={12} className="text-accent-sage" /> Employee Account (jdoe)
              </span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-mono bg-app-void text-slate-300 border border-card-border">
                <Globe size={12} className="text-accent-amber" /> External IP: 203.0.113.66
              </span>
            </div>
          </div>

          {/* Recommendation Box */}
          <div className="p-4 rounded-xl bg-accent-amber/5 border border-accent-amber/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <p className="text-xs font-bold text-accent-amber uppercase tracking-wider mb-0.5">
                NOCTRA Recommendation
              </p>
              <p className="text-xs text-content-primary font-mono font-bold">
                {latestCase?.proposed_action?.action_type || "REVOKE_CREDENTIALS"} ({latestCase?.proposed_action?.target || "account:jdoe@acme.com"})
              </p>
            </div>
            <Button
              variant="primary"
              onClick={() => navigate(latestCase ? `/case/${latestCase.id}` : "/feed")}
              className="bg-accent-amber hover:bg-accent-amber-hover text-app-bg font-bold text-xs px-5 py-2.5 rounded-xl shrink-0"
            >
              Review & Approve Action <ArrowRight size={14} className="ml-1.5" />
            </Button>
          </div>
        </div>

        {/* Right Span: Handled Today & Operations Overview */}
        <div className="lg:col-span-4 space-y-6">
          
          {/* Handled Today Stream */}
          <div className="bg-card-bg rounded-2xl border border-card-border p-5 shadow-card space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Handled Today
            </h3>
            <div className="space-y-3">
              <div className="p-3 rounded-xl bg-app-void border border-card-border space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-200 font-mono">Case #103</span>
                  <span className="text-[10px] text-emerald-400 font-bold flex items-center gap-1">
                    <CheckCircle2 size={12} /> Approved
                  </span>
                </div>
                <p className="text-xs text-slate-400">Blocked Suspicious IP 198.51.100.42</p>
              </div>

              <div className="p-3 rounded-xl bg-app-void border border-card-border space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-200 font-mono">Case #102</span>
                  <span className="text-[10px] text-slate-400 font-bold flex items-center gap-1">
                    <XCircle size={12} /> Dismissed
                  </span>
                </div>
                <p className="text-xs text-slate-400">Phishing Email Warning Dismissed</p>
              </div>
            </div>
          </div>

          {/* Operational Status */}
          <div className="bg-card-bg rounded-2xl border border-card-border p-5 shadow-card">
            <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
              NOCTRA Platform Status
            </span>
            <div className="mt-3 flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs font-bold text-slate-200">
                All 4 Security Connectors Active
              </span>
            </div>
          </div>

        </div>
      </div>

      {/* Security Tooling Connectors Section */}
      <div className="bg-card-bg rounded-2xl border border-card-border p-6 shadow-card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-bold text-content-primary flex items-center gap-2 font-display">
              <ShieldCheck size={16} className="text-accent-amber" /> Integrated Security Connectors
            </h2>
            <p className="text-xs text-content-secondary mt-0.5">
              Real-time security telemetry feeding NOCTRA's reasoning engine.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {connectors.map((conn) => (
            <div
              key={conn.id}
              className="p-4 rounded-xl bg-app-void border border-card-border flex flex-col justify-between space-y-3"
            >
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-slate-200 truncate">
                    {conn.name}
                  </span>
                  <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 text-[10px] font-bold rounded-full border border-emerald-500/20">
                    {conn.status}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400">{conn.category}</p>
              </div>

              <div className="flex items-center justify-between text-[11px] text-slate-400 border-t border-card-border pt-2">
                <span>{conn.assets_monitored} assets</span>
                <button
                  type="button"
                  onClick={() => handleSyncConnector(conn.id)}
                  disabled={syncingId === conn.id}
                  className="flex items-center gap-1 text-accent-amber font-semibold hover:underline text-[11px]"
                >
                  <RefreshCw size={10} className={syncingId === conn.id ? "animate-spin" : ""} />
                  {conn.last_sync}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default BriefPage;
