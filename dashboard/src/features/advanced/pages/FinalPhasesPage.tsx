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
    { id: "retention", label: "Retention P81", icon: FileArchive },
    { id: "coverage", label: "ATT&CK Coverage P82", icon: Shield },
    { id: "collab", label: "Agent-to-Agent P83", icon: Users },
    { id: "tv", label: "SOC TV Wall P84", icon: Monitor },
  ] as const;

  return (
    <div className="space-y-6">
      <PageHeader title="Final Phases 81-84" description="Data Retention & Legal Hold automation, ATT&CK Coverage Dashboard, Agent-to-Agent collaboration, Real-time SOC TV wall" />

      <div className="p-4 bg-accent-primary/10 border border-accent-primary/30 rounded text-sm">
        <div className="font-bold mb-2">Understanding 81-84:</div>
        <ul className="list-disc ml-5 space-y-1 text-xs">
          <li><b>81 Retention & Legal Hold:</b> DataRetentionPolicy data_type retention_days archive_after_days delete_after_days, DataArchiveLog s3://archive/[org_id]/[data_type]/[date].json, LegalHold name case_ids is_active, GDPRDeletionRequest target_email status. Automation run archives old data respecting legal holds (held case_ids not archived), ensures partitions via ensure_partitions(). Endpoint /data-lifecycle/automation/run.</li>
          <li><b>82 ATT&CK Coverage:</b> ATT&CK matrix subset 14 techniques (T1078 Valid Accounts, T1059.001 PowerShell, T1053.005 Scheduled Task, T1003.001 LSASS, etc). AttackCoverage per technique has_detection_rule/hunt/playbook/purple_exercise detection_count coverage_score 0-100 (25 per type +10 if alerts). Gap analysis if score&lt;50. Report total/covered/percent + tactic breakdown + gaps list.</li>
          <li><b>83 Agent-to-Agent:</b> AgentCollaboration case_id name agents_json [hunter,enricher,responder,compliance_checker,risk_analyst] status running/completed result_json consensus/votes consensus_score, AgentMessage from_agent/to_agent message_type proposal/vote/tool_result content tool_name/tool_output confidence. Run round: hunter runs hunt query, enricher threat intel, responder propose isolate, risk_analyst metrics, then voting consensus escalate if majority.</li>
          <li><b>84 SOC TV Wall:</b> SOCWallConfig name widgets_json [[type alert_feed/open_cases/risk_metrics/attack_heatmap/agent_status/world_map position x,y,w,h config] is_default, SOCWallMetric metric_name metric_value recorded_at. Seed default wall 6 widgets. Live metrics: total_alerts, alerts_last_hour/24h, open_cases, critical, alerts_per_minute, top_sources, severity_breakdown, recent_alerts 10. TV page polls 5s, black background for wall display.</li>
        </ul>
      </div>

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
