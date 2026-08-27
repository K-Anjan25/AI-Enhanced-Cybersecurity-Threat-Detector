import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Sparkles,
  AlertTriangle,
  Server,
  User as UserIcon,
  Globe,
  AppWindow,
  CheckCircle2,
  Bell,
  Activity,
  ShieldCheck,
  RefreshCw,
  ChevronRight,
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
      {/* Simulation Controls Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-white p-4 rounded-xl border border-line-subtle shadow-card">
        <div>
          <h1 className="text-xl font-bold font-display text-content-primary">
            Dashboard
          </h1>
          <p className="text-xs text-content-secondary mt-0.5">
            Real-time security posture and automated AI incident analysis.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedScenario}
            onChange={(e) => setSelectedScenario(e.target.value)}
            disabled={simulating}
            className="bg-slate-100 border border-slate-200 text-xs text-slate-800 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="credential_leak">Credential Leak (T1078)</option>
            <option value="phishing_outbreak">Phishing Outbreak (T1566)</option>
            <option value="data_exfiltration">Data Exfiltration (T1048)</option>
            <option value="compromised_api_key">Compromised API Key (T1098)</option>
          </select>
          <Button variant="primary" onClick={handleSimulate} disabled={simulating} className="bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs px-4 py-2 rounded-lg">
            <Sparkles size={14} className="mr-1.5" aria-hidden />
            {simulating ? "Simulating…" : "Simulate Incident"}
          </Button>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-600 font-medium">
          {error}
        </div>
      )}

      {/* Main 3-Column Bento Layout (Exact layout from screenshot) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Column 1: Security Posture Score (White Card with Royal Blue Ring) */}
        <div className="lg:col-span-4 bg-white rounded-2xl border border-line-subtle p-6 shadow-card flex flex-col items-center justify-between min-h-[340px]">
          <h2 className="text-base font-bold text-slate-900 self-start">
            Security Posture Score
          </h2>

          <div className="relative my-4 flex items-center justify-center w-48 h-48">
            <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
              <path
                className="text-slate-100"
                strokeWidth="3.5"
                stroke="currentColor"
                fill="none"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <path
                className="text-blue-600"
                strokeDasharray="96, 100"
                strokeWidth="3.5"
                strokeLinecap="round"
                stroke="currentColor"
                fill="none"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
            </svg>
            <div className="absolute flex flex-col items-center justify-center">
              <span className="text-4xl font-extrabold text-slate-900 font-display">
                96<span className="text-slate-400 text-2xl font-semibold">/100</span>
              </span>
            </div>
          </div>

          <p className="text-sm font-medium text-slate-500">
            Overall Health: <span className="text-slate-800 font-semibold">Good</span>
          </p>
        </div>

        {/* Column 2: Center Dark Navy Card (Latest Incident) */}
        <div className="lg:col-span-5 bg-[#0e1320] text-white rounded-2xl p-6 shadow-navy flex flex-col justify-between min-h-[340px]">
          <div>
            <span className="text-[11px] font-bold tracking-wider text-slate-400 uppercase">
              LATEST INCIDENT
            </span>

            <div className="flex items-center gap-2 mt-3 mb-3">
              <AlertTriangle size={18} className="text-slate-200" />
              <h2 className="text-base font-bold text-white font-display">
                {latestCase?.analysis?.headline || latestCase?.title || "Anomaly Detected (High Priority)"}
              </h2>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed font-normal mb-5">
              {latestCase?.analysis?.what_happened ||
                latestCase?.description ||
                "Potential automated brute-force attack blocked on primary authentication server. No credentials compromised; suspicious activity originated from a known threat IP (185.122.34.8) at 14:32 UTC."}
            </p>

            <div className="space-y-2">
              <p className="text-[11px] font-semibold text-slate-300">
                Affected Assets (Blast Radius):
              </p>
              <div className="flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono bg-slate-800/80 text-slate-200 border border-slate-700">
                  <Server size={12} className="text-slate-400" /> Server: Auth-Srv-01
                </span>
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono bg-slate-800/80 text-slate-200 border border-slate-700">
                  <UserIcon size={12} className="text-slate-400" /> User: sysadmin
                </span>
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono bg-slate-800/80 text-slate-200 border border-slate-700">
                  <Globe size={12} className="text-slate-400" /> IP: 10.0.1.50
                </span>
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono bg-slate-800/80 text-slate-200 border border-slate-700">
                  <AppWindow size={12} className="text-slate-400" /> Application: Portal
                </span>
              </div>
            </div>
          </div>

          <div className="mt-6 flex justify-end">
            <button
              type="button"
              onClick={() => navigate(latestCase ? `/case/${latestCase.id}` : "/feed")}
              className="bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs px-5 py-2.5 rounded-lg transition-colors shadow-cobalt"
            >
              Remediate Incident
            </button>
          </div>
        </div>

        {/* Column 3: Right Dark Navy Cards (Recent Alerts & Platform Status) */}
        <div className="lg:col-span-3 flex flex-col gap-4 min-h-[340px]">
          
          {/* Recent Alerts Card */}
          <div className="bg-[#0e1320] text-white rounded-2xl p-5 shadow-navy flex-1 flex flex-col justify-between">
            <div>
              <span className="text-[11px] font-bold tracking-wider text-slate-400 uppercase">
                RECENT ALERTS
              </span>
              <div className="mt-3 space-y-3">
                <div className="flex items-center justify-between text-xs py-1 border-b border-slate-800">
                  <span className="text-slate-200 font-medium">SQL Injection Attempt</span>
                  <span className="text-slate-400 font-mono text-[11px]">14:15</span>
                </div>
                <div className="flex items-center justify-between text-xs py-1 border-b border-slate-800">
                  <span className="text-slate-200 font-medium">Suspicious API Activity</span>
                  <span className="text-slate-400 font-mono text-[11px]">13:58</span>
                </div>
                <div className="flex items-center justify-between text-xs py-1">
                  <span className="text-slate-200 font-medium">Network Scan</span>
                  <span className="text-slate-400 font-mono text-[11px]">13:30</span>
                </div>
              </div>
            </div>
          </div>

          {/* Platform Status Card */}
          <div className="bg-[#0e1320] text-white rounded-2xl p-5 shadow-navy">
            <span className="text-[11px] font-bold tracking-wider text-slate-400 uppercase">
              PLATFORM STATUS
            </span>
            <div className="mt-3 flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs font-semibold text-slate-200">
                All Systems Operational
              </span>
            </div>
          </div>

        </div>
      </div>

      {/* Security Tooling Connectors Section */}
      <div className="bg-white rounded-2xl border border-line-subtle p-6 shadow-card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2 font-display">
              <ShieldCheck size={16} className="text-blue-600" /> Integrated Security Tooling
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Live telemetry feeding automated decision engine.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {connectors.map((conn) => (
            <div
              key={conn.id}
              className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col justify-between space-y-3"
            >
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-slate-800 truncate">
                    {conn.name}
                  </span>
                  <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 text-[10px] font-bold rounded-full">
                    {conn.status}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500">{conn.category}</p>
              </div>

              <div className="flex items-center justify-between text-[11px] text-slate-600 border-t border-slate-200 pt-2">
                <span>{conn.assets_monitored} assets</span>
                <button
                  type="button"
                  onClick={() => handleSyncConnector(conn.id)}
                  disabled={syncingId === conn.id}
                  className="flex items-center gap-1 text-blue-600 font-semibold hover:underline text-[11px]"
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
