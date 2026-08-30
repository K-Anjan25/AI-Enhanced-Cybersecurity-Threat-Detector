import React, { useEffect, useState } from "react";
import { Card, Button, PageHeader, Spinner } from "../../../components/ui";
import { Shield, Users, Monitor, FileArchive, Layers } from "lucide-react";
import apiClient from "../../../api/client";

const api = {
  retentionPolicies: () => apiClient.get("/data-lifecycle/policies"),
  runRetention: () => apiClient.post("/data-lifecycle/automation/run"),
  coverage: () => apiClient.get("/attack-coverage/"),
  coverageReport: () => apiClient.post("/attack-coverage/report"),
  collabs: () => apiClient.get("/agent-collab/"),
  socLive: () => apiClient.get("/soc-tv/live"),
};

type Tab = "retention" | "coverage" | "collab" | "tv";

export default function FinalPhasesPage() {
  const [tab, setTab] = useState<Tab>("retention");
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
        case "retention": res = await api.retentionPolicies(); break;
        case "coverage": res = await api.coverage(); break;
        case "collab": res = await api.collabs(); break;
        case "tv": res = await api.socLive(); break;
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
    { id: "retention", label: "Retention", icon: FileArchive },
    { id: "coverage", label: "ATT&CK Coverage", icon: Shield },
    { id: "collab", label: "Agent-to-Agent", icon: Users },
    { id: "tv", label: "SOC TV Wall", icon: Monitor },
  ] as const;

  return (
    <div className="space-y-6">
      <PageHeader title="Coverage & Collaboration Labs" description="Data retention and legal hold, ATT&CK coverage, agent-to-agent collaboration and the live SOC wall." />

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
              <h3 className="font-bold text-lg capitalize flex items-center gap-2"><Layers size={16} />{tab}</h3>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => load(tab)}>Refresh</Button>
                {tab === "retention" && <Button size="sm" onClick={async()=>{ const r=await api.runRetention(); setExtra(r.data); }}>Run Automation</Button>}
                {tab === "coverage" && <Button size="sm" onClick={async()=>{ const r=await api.coverageReport(); setExtra(r.data); }}>Gen Report</Button>}
                {tab === "tv" && <Button size="sm" onClick={()=>window.open("/soc-tv-wall", "_blank")}>Open TV Wall</Button>}
              </div>
            </div>

            <div className="text-xs space-y-2">
              {tab === "retention" && <><p>Policies: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Retention 90d alerts, 365d cases, archive after 60d/180d, respects legal holds</p></>}
              {tab === "coverage" && <><p>Techniques: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Coverage score 0-100, gap if &lt;50, tactic breakdown initial-access/execution/persistence etc</p></>}
              {tab === "collab" && <><p>Collaborations: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Multi-agent: hunter, enricher, responder, compliance_checker, risk_analyst voting consensus</p></>}
              {tab === "tv" && <><p>Live: {data?.total_alerts ?? 0} alerts, {data?.open_cases ?? 0} open cases, {data?.alerts_per_minute ?? 0}/min</p><p className="text-content-tertiary">TV wall black theme, auto-refresh 5s, widgets alert_feed/open_cases/risk_metrics/heatmap</p></>}
            </div>

            <pre className="mt-6 p-4 bg-app-subtle rounded text-xs overflow-auto max-h-[400px] border border-line-subtle">{JSON.stringify(data, null, 2)}</pre>
            {extra && <pre className="mt-3 p-4 bg-app-surface border border-accent-primary/30 rounded text-xs overflow-auto max-h-[300px]">{JSON.stringify(extra, null, 2)}</pre>}
          </div>
        )}
      </Card>
    </div>
  );
}
