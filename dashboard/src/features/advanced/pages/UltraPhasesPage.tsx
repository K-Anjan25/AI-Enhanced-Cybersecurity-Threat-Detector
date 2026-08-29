import React, { useEffect, useState } from "react";
import { Card, Button, PageHeader, Spinner } from "../../../components/ui";
import { CheckCheck, BookOpen, Globe, ShieldAlert } from "lucide-react";
import apiClient from "../../../api/client";

const api = {
  approvalWfs: () => apiClient.get("/approval-workflows/"),
  approvalInstances: () => apiClient.get("/approval-workflows/instances"),
  notebooks: () => apiClient.get("/hunt-notebooks/"),
  exposures: () => apiClient.get("/exposure/"),
  exposureSummary: () => apiClient.get("/exposure/summary"),
  redteamJobs: () => apiClient.get("/ai-redteam/jobs"),
};

type Tab = "approval" | "notebook" | "exposure" | "redteam";

export default function UltraPhasesPage() {
  const [tab, setTab] = useState<Tab>("approval");
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
        case "approval": res = await api.approvalWfs(); break;
        case "notebook": res = await api.notebooks(); break;
        case "exposure": res = await api.exposureSummary(); break;
        case "redteam": res = await api.redteamJobs(); break;
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
    { id: "approval", label: "Approval WF P85", icon: CheckCheck },
    { id: "notebook", label: "Notebook P86", icon: BookOpen },
    { id: "exposure", label: "Exposure ASM P87", icon: Globe },
    { id: "redteam", label: "AI Red Team P88", icon: ShieldAlert },
  ] as const;

  return (
    <div className="space-y-6">
      <PageHeader title="Ultra Phases 85-88" description="SOAR Approval Workflows, Threat Hunting Notebook (Jupyter), Exposure Management ASM, AI Red Team adversarial LLM" />

      <div className="p-4 bg-accent-primary/10 border border-accent-primary/30 rounded text-sm">
        <div className="font-bold mb-2">Understanding 85-88:</div>
        <ul className="list-disc ml-5 space-y-1 text-xs">
          <li><b>85 Approval Workflows:</b> ApprovalWorkflow name steps_json [{`{step, name, approver_roles [admin], action_types [block_ip, isolate_host], min_approvals}`}] trigger_json {`{severity [HIGH,CRITICAL], action_types}`}, ApprovalInstance workflow_id soar_action_id case_id action_type target current_step status pending/approved/rejected approvals_json [{`{user_id, decision, comment, at}`}], ApprovalTask step assignee_role status. Seed Critical Action SOC Lead + Compliance Dual Approval. Request creates tasks for first step, approve moves to next step or completes, if linked SoarAction status approved.</li>
          <li><b>86 Hunting Notebook:</b> HuntNotebook name kernel python/kql/sql tags, NotebookCell cell_type code/markdown/kql/sql position source output_json {`{stdout, stderr, result_count}`} execution_count status, NotebookExecution. Seed Threat Hunting Starter with markdown + KQL severity:CRITICAL AND source:okta + python cell. Execute cell: kql runs hunt_service.execute_hunt_query, python mock safe (blocks os/sys import), markdown rendered. Execute notebook runs all non-markdown cells.</li>
          <li><b>87 Exposure ASM:</b> ASM_Domain domain discovery_method manual/brute_force/cert_transparency, ASM_AssetExposure domain_id asset_type host/domain/ip/service/certificate name ip port service exposure_type open_port/expired_cert/exposed_service/misconfig severity description evidence_json {`{banner, cert_expiry}`}, ASM_Certificate domain issuer not_before/after expired/self_signed san, ExposureFinding. Discover mock 4 exposures: 443 https LOW, 22 ssh MEDIUM, 8080 admin panel HIGH, expired cert MEDIUM 7d. Summary total/open/high/critical/expired_certs risk_score.</li>
          <li><b>88 AI Red Team:</b> RedTeamJob name target_model claude-sonnet-5 attack_types [prompt_injection,jailbreak,data_exfiltration,tool_abuse] status total_prompts successful/blocked risk_score results_json, RedTeamPrompt job_id attack_type prompt expected_behavior refuse response was_successful/was_blocked evaluation_json, RedTeamFinding. Library ADVERSARIAL_PROMPTS 3 per type: ignore previous instructions, DAN, email of user case 1, block_ip 0.0.0.0/0 etc. Run job mocks evaluation: all blocked except borderline fictional story allowed with safe completion, tool abuse blocked via approval workflow. Creates finding if attack succeeded.</li>
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
                {tab === "approval" && <Button size="sm" onClick={async()=>{ const r=await api.approvalInstances(); setExtra(r.data); }}>Instances</Button>}
                {tab === "exposure" && <Button size="sm" onClick={async()=>{ const r=await api.exposures(); setExtra(r.data); }}>List Exposures</Button>}
              </div>
            </div>

            <div className="text-xs space-y-2">
              {tab === "approval" && <><p>Workflows: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Critical SOC Lead + Dual Approval, request creates tasks, approve moves steps, links to SoarAction</p></>}
              {tab === "notebook" && <><p>Notebooks: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Jupyter-like: markdown, KQL executes hunt, python mock safe, execute all cells</p></>}
              {tab === "exposure" && <><p>Summary: {data?.total_exposures ?? 0} total, {data?.critical ?? 0} critical, risk {data?.risk_score ?? 0}</p><p className="text-content-tertiary">Mock discovery: 443, 22 ssh, 8080 admin HIGH, expired cert, Shodan/Censys real impl would query</p></>}
              {tab === "redteam" && <><p>Jobs: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Adversarial prompts: prompt_injection, jailbreak, data_exfiltration, tool_abuse, all blocked via guardrails + approval WF</p></>}
            </div>

            <pre className="mt-6 p-4 bg-app-subtle rounded text-xs overflow-auto max-h-[400px] border border-line-subtle">{JSON.stringify(data, null, 2)}</pre>
            {extra && <pre className="mt-3 p-4 bg-app-surface border border-accent-primary/30 rounded text-xs overflow-auto max-h-[300px]">{JSON.stringify(extra, null, 2)}</pre>}
          </div>
        )}
      </Card>
    </div>
  );
}
