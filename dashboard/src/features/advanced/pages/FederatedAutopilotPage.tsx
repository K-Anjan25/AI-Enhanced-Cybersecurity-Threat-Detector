import React, { useEffect, useState } from "react";
import { Card, Button, PageHeader, Spinner } from "../../../components/ui";
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
    { id: "federated", label: "Federated Learning P89", icon: Share2 },
    { id: "autopilot", label: "Compliance Autopilot P90", icon: Wrench },
  ] as const;

  return (
    <div className="space-y-6">
      <PageHeader title="Final 89-90: Federated + Autopilot" description="Federated Learning across orgs (privacy-preserving) + Compliance Autopilot auto-remediate CIS" />

      <div className="p-4 bg-accent-primary/10 border border-accent-primary/30 rounded text-sm">
        <div className="font-bold mb-2">Understanding 89-90:</div>
        <ul className="list-disc ml-5 space-y-1 text-xs">
          <li><b>89 Federated Learning:</b> FederatedJob name model_type threat_detection base_model noctra-ml-v1 config [rounds 5, min_orgs 2, aggregation fedavg, dp_noise 0.1] status pending/running/aggregating/completed current_round/total_rounds global_model_id global_metrics accuracy/f1 participating_orgs. FederatedRound round_number status training/aggregating/completed metrics avg_accuracy/f1. OrgModelUpdate job_id round_id org_id update_json weights_hash sample_count metrics accuracy/f1 status pending/submitted/aggregated is_private DP noise + secure aggregation. FederatedModel version model_id s3_key is_global. Flow: create job - start round creates pending updates for 5 orgs - orgs submit update (weights_hash + metrics) - aggregate FedAvg avg_accuracy - if last round create global model. Privacy: raw data never leaves org, only model deltas, DP noise 0.1.</li>
          <li><b>90 Compliance Autopilot:</b> AutopilotRule name control_id CIS-2.1/CIS-4.1/CIS-3.1/CIS-1.4 benchmark CIS severity remediation_json [action_type close_s3_public/restrict_sg_ingress/enable_cloudtrail/rotate_iam_keys params approval_required rollback_action] is_active dry_run require_approval auto_remediate_count. Seed 4: Auto close S3 public CRITICAL dry_run true require_approval true, Auto restrict SG 0.0.0.0/0 HIGH dry_run false, Enable CloudTrail MEDIUM, Rotate IAM keys MEDIUM dry_run true. AutopilotExecution rule_id violation_id action_type target status pending/approved/executed/failed/dry_run result_json success/before/after/rollback_id executed_by approval_instance_id. evaluate_violations matches open CSPM violations by control_id/benchmark creates executions, if require_approval and CRITICAL/HIGH creates ApprovalWorkflow instance (Critical Action). execute_autopilot checks approval, if dry_run only logs would_execute, else marks executed, marks violation fixed, increments rule counter, creates finding. Summary total_rules/total_executions/executed/dry_run/pending/open_violations auto_remediation_rate.</li>
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

            <pre className="mt-6 p-4 bg-app-subtle rounded text-xs overflow-auto max-h-[400px] border border-line-subtle">{JSON.stringify(data, null, 2)}</pre>
            {extra && <pre className="mt-3 p-4 bg-app-surface border border-accent-primary/30 rounded text-xs overflow-auto max-h-[300px]">{JSON.stringify(extra, null, 2)}</pre>}
          </div>
        )}
      </Card>
    </div>
  );
}
