import React, { useEffect, useState } from "react";
import { Card, Button, PageHeader, Spinner } from "../../../components/ui";
import { Shield, Search, Bug, Bot, Fingerprint, Cloud, Package, EyeOff, FileSearch, Share2, FileCheck, BarChart3 } from "lucide-react";
import apiClient from "../../../api/client";

const api = {
  itdrThreats: () => apiClient.get("/itdr/threats"),
  cspmViolations: () => apiClient.get("/cspm/violations"),
  cspmEvaluate: () => apiClient.post("/cspm/evaluate"),
  sboms: () => apiClient.get("/sbom/"),
  deceptionAlerts: () => apiClient.get("/deception/alerts"),
  forensicsCases: () => apiClient.get("/forensics/cases"),
  tipFeeds: () => apiClient.get("/tip/feeds"),
  tipStix: () => apiClient.get("/tip/stix"),
  complianceControls: () => apiClient.get("/compliance-continuous/controls"),
  complianceAssess: (fw: string) => apiClient.post(`/compliance-continuous/assess/${fw}`),
  execMetrics: () => apiClient.get("/exec-risk/metrics"),
  execBoardPack: () => apiClient.post("/exec-risk/board-pack"),
  execRoi: () => apiClient.get("/exec-risk/roi"),
};

type Tab = "itdr" | "cspm" | "sbom" | "deception" | "forensics" | "tip" | "compliance" | "exec";

export default function FuturePhasesPage() {
  const [tab, setTab] = useState<Tab>("itdr");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extra, setExtra] = useState<any>(null);

  const load = async (t: Tab) => {
    setLoading(true);
    setError(null);
    try {
      let res: any;
      switch (t) {
        case "itdr": res = await api.itdrThreats(); break;
        case "cspm": res = await api.cspmViolations(); break;
        case "sbom": res = await api.sboms(); break;
        case "deception": res = await api.deceptionAlerts(); break;
        case "forensics": res = await api.forensicsCases(); break;
        case "tip": res = await api.tipStix(); break;
        case "compliance": res = await api.complianceControls(); break;
        case "exec": res = await api.execMetrics(); break;
      }
      setData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(tab); }, [tab]);

  const tabs = [
    { id: "itdr", label: "ITDR", icon: Fingerprint },
    { id: "cspm", label: "CSPM", icon: Cloud },
    { id: "sbom", label: "SBOM", icon: Package },
    { id: "deception", label: "Deception", icon: EyeOff },
    { id: "forensics", label: "Forensics", icon: FileSearch },
    { id: "tip", label: "TIP", icon: Share2 },
    { id: "compliance", label: "Cont Comp", icon: FileCheck },
    { id: "exec", label: "Exec Risk", icon: BarChart3 },
  ] as const;

  return (
    <div className="space-y-6">
      <PageHeader title="Cloud & Compliance Labs" description="Identity threat detection, cloud posture, software supply chain, deception, forensics, threat intel platform, continuous compliance and executive risk." />

      <div className="flex flex-wrap gap-2">
        {tabs.map(t => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id as Tab)} className={`flex items-center gap-2 px-3 py-2 rounded text-xs font-semibold border transition ${tab === t.id ? "bg-accent-primary text-black border-accent-primary" : "bg-app-surface border-line-subtle text-content-secondary"}`}>
              <Icon size={14} /> {t.label}
            </button>
          );
        })}
      </div>

      <Card className="p-6 min-h-[400px]">
        {loading && <div className="flex justify-center py-20"><Spinner /></div>}
        {error && <div className="text-red-400 text-sm p-4 border border-red-500/30 rounded bg-red-500/10">{error}</div>}
        {!loading && !error && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-lg capitalize">{tab}</h3>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => load(tab)}>Refresh</Button>
                {tab === "cspm" && <Button size="sm" onClick={async()=>{ const r=await api.cspmEvaluate(); setExtra(r.data); }}>Evaluate CIS</Button>}
                {tab === "compliance" && <Button size="sm" onClick={async()=>{ const r=await api.complianceAssess("SOC2"); setExtra(r.data); }}>Run Assessment</Button>}
                {tab === "exec" && <><Button size="sm" onClick={async()=>{ const r=await api.execBoardPack(); setExtra(r.data); }}>Gen Board Pack</Button><Button variant="secondary" size="sm" onClick={async()=>{ const r=await api.execRoi(); setExtra(r.data); }}>ROI</Button></>}
              </div>
            </div>

            {tab === "itdr" && <div className="text-xs space-y-2"><p>Threats: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Baseline built from 30d audit logs, impossible travel &lt;3600s different geo flagged HIGH.</p></div>}
            {tab === "cspm" && <div className="text-xs space-y-2"><p>Violations: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">CIS checks: S3 public, SG 0.0.0.0/0, root usage, CloudTrail.</p></div>}
            {tab === "sbom" && <div className="text-xs space-y-2"><p>SBOMs: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">CycloneDX parse, risk on log4j/openssl.</p></div>}
            {tab === "deception" && <div className="text-xs space-y-2"><p>Alerts: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Honeypot interaction increments, canary trigger via token value.</p></div>}
            {tab === "forensics" && <div className="text-xs space-y-2"><p>Cases: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Case linked, artifact SHA256, timeline sorted asc.</p></div>}
            {tab === "tip" && <div className="text-xs space-y-2"><p>STIX objects: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">STIX 2.1 bundle ingest, export, MISP events.</p></div>}
            {tab === "compliance" && <div className="text-xs space-y-2"><p>Controls: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">SOC2 CC6.1/6.2/7.2/8.1, evidence from audit_logs, score compliant/total*100.</p></div>}
            {tab === "exec" && <div className="text-xs space-y-2"><p>Metrics: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">MTTD, high alerts, avg vuln risk, board pack JSON, ROI hours/dollars.</p></div>}

            <pre className="mt-6 p-4 bg-app-subtle rounded text-xs overflow-auto max-h-[400px] border border-line-subtle">{JSON.stringify(data, null, 2)}</pre>
            {extra && <pre className="mt-3 p-4 bg-app-surface border border-accent-primary/30 rounded text-xs overflow-auto max-h-[300px]">{JSON.stringify(extra, null, 2)}</pre>}
          </div>
        )}
      </Card>
    </div>
  );
}
