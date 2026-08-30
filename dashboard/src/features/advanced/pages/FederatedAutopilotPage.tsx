import React, { useEffect, useState } from "react";
import { Card, Button, PageHeader, Spinner } from "../../../components/ui";
import { RawData } from "../../../components/ui";
import { Share2, Wrench } from "lucide-react";
import apiClient from "../../../api/client";

const api = {
  fedJobs: () => apiClient.get("/federated/jobs"),
  fedCreate: () => apiClient.post("/federated/jobs", { name: "Federated Threat Detection", description: "Cross-org federated learning for threat detection without sharing raw data", model_type: "threat_detection", total_rounds: 3 }),
  autopilotRules: () => apiClient.get("/compliance-autopilot/rules"),
  autopilotEvaluate: () => apiClient.post("/compliance-autopilot/evaluate"),
  autopilotSummary: () => apiClient.get("/compliance-autopilot/summary"),
  autopilotExecutions: () => apiClient.get("/compliance-autopilot/executions"),
};

type Tab = "federated" | "autopilot";

export default function FederatedAutopilotPage() {
  const [tab, setTab] = useState<Tab>("federated");
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
        case "federated": res = await api.fedJobs(); break;
        case "autopilot": res = await api.autopilotSummary(); break;
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
    { id: "federated", label: "Federated Learning", icon: Share2 },
    { id: "autopilot", label: "Compliance Autopilot", icon: Wrench },
  ] as const;

  return (
    <div className="space-y-6">
      <PageHeader title="Federation & Autopilot Labs" description="Privacy-preserving learning across tenants and automatic remediation of compliance drift." />

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
                {tab === "federated" && <Button size="sm" onClick={async()=>{ const r=await api.fedCreate(); setExtra(r.data); }}>Create Job</Button>}
                {tab === "autopilot" && <><Button size="sm" onClick={async()=>{ const r=await api.autopilotEvaluate(); setExtra(r.data); }}>Evaluate Violations</Button><Button variant="secondary" size="sm" onClick={async()=>{ const r=await api.autopilotRules(); setExtra(r.data); }}>Rules</Button><Button variant="secondary" size="sm" onClick={async()=>{ const r=await api.autopilotExecutions(); setExtra(r.data); }}>Executions</Button></>}
              </div>
            </div>

            <div className="text-xs space-y-2">
              {tab === "federated" && <><p>Jobs: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Privacy-preserving: raw data stays in org, only model deltas shared, FedAvg aggregation, DP noise, secure aggregation, global model after N rounds</p></>}
              {tab === "autopilot" && <><p>Summary: {data?.total_rules ?? 0} rules, {data?.executed ?? 0} executed, {data?.pending ?? 0} pending, {data?.open_violations ?? 0} open violations, rate {data?.auto_remediation_rate?.toFixed(1) ?? 0}%</p><p className="text-content-tertiary">Auto-remediate CIS: close S3 public, restrict SG, enable CloudTrail, rotate IAM keys, dry_run + approval for CRITICAL, rollback_id</p></>}
            </div>

            <RawData value={data} />
            <RawData value={extra} label="Result" />
          </div>
        )}
      </Card>
    </div>
  );
}
