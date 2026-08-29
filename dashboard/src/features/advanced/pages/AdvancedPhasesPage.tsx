import React, { useEffect, useState } from "react";
import { Card, Button, PageHeader, Spinner } from "../../../components/ui";
import { Database, Radio, Store, Brain, ShieldAlert, Swords, FileDown, Layers } from "lucide-react";
import apiClient from "../../../api/client";

const api = {
  partitioningStatus: () => apiClient.get("/ha/status"),
  dataLakeExports: () => apiClient.get("/data-lake/exports"),
  dataLakeExport: () => apiClient.post("/data-lake/export", {}),
  dataLakeQuery: (sql: string) => apiClient.post("/data-lake/query", { athena_sql: sql }),
  haMessages: () => apiClient.get("/ha/messages"),
  haNodes: () => apiClient.get("/ha/nodes"),
  marketplace: () => apiClient.get("/marketplace/"),
  finetuneJobs: () => apiClient.get("/finetune/jobs"),
  riskAssets: () => apiClient.get("/risk-based/assets"),
  purpleExercises: () => apiClient.get("/purple-team/exercises"),
  pdfExports: () => apiClient.get("/pdf-export/"),
};

type Tab = "partition" | "datalake" | "ha" | "marketplace" | "finetune" | "risk" | "purple" | "pdf";

export default function AdvancedPhasesPage() {
  const [tab, setTab] = useState<Tab>("partition");
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
        case "partition": res = await api.partitioningStatus(); break;
        case "datalake": res = await api.dataLakeExports(); break;
        case "ha": res = await api.haMessages(); break;
        case "marketplace": res = await api.marketplace(); break;
        case "finetune": res = await api.finetuneJobs(); break;
        case "risk": res = await api.riskAssets(); break;
        case "purple": res = await api.purpleExercises(); break;
        case "pdf": res = await api.pdfExports(); break;
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
    { id: "partition", label: "Partition P73", icon: Database },
    { id: "datalake", label: "Data Lake P73", icon: Database },
    { id: "ha", label: "HA Bus P74", icon: Radio },
    { id: "marketplace", label: "Marketplace P75", icon: Store },
    { id: "finetune", label: "FineTune P76", icon: Brain },
    { id: "risk", label: "Risk-Based P77", icon: ShieldAlert },
    { id: "purple", label: "Purple Team P78-79", icon: Swords },
    { id: "pdf", label: "PDF Export P80", icon: FileDown },
  ] as const;

  return (
    <div className="space-y-6">
      <PageHeader title="Advanced Phases 73-80" description="Partitioning, Data Lake S3 Parquet, HA Redis Event Bus, SOAR Marketplace, LLM Fine-tune, Risk-Based Alerting, Purple Team, PDF Board Pack" />

      <div className="p-4 bg-accent-primary/10 border border-accent-primary/30 rounded text-sm">
        <div className="font-bold mb-2">Understanding 73-80:</div>
        <ul className="list-disc ml-5 space-y-1 text-xs">
          <li><b>73 Partitioning:</b> Monthly RANGE partitions for security_alerts, audit_logs, scanned_alerts, hunt_executions, vuln_scans, event_bus_messages. Postgres only, guarded by DB_PARTITIONING_ENABLED. Ensures partition pruning via org_id + created_at composite index. Script in app/core/partitioning.py creates next 3 months.</li>
          <li><b>73 Data Lake:</b> Export alerts to S3 Parquet s3://noctra-datalake/datalake/org_id=1/year=2026/month=08/alerts.parquet (pyarrow+boto3 mock), DataLakeExport metadata, Athena SQL mock query (SELECT * FROM security_alerts WHERE org_id=1).</li>
          <li><b>74 HA Bus:</b> Redis pub/sub + DB persistence fallback. EventBus.publish(channel, event_type, payload) writes EventBusMessage + redis.publish. HANode heartbeat for multi-region primary/replica. /ha/status shows redis_connected.</li>
          <li><b>75 Marketplace:</b> MarketplacePlaybook (name, category response/enrichment/containment, tags, playbook_json steps, downloads, rating, verified), seed 4 defaults (Auto Block IP, VT Enrich, Isolate Host, Phishing Response), install creates local SoarPlaybook + increments downloads.</li>
          <li><b>76 Fine-tune:</b> FineTuneDataset from cases/alerts (record_count, preview), FineTuneJob base_model claude-sonnet-5, config epochs/lr, mock training progress 100% + metrics loss 0.12 acc 0.94, result_model_id ft-...</li>
          <li><b>77 Risk-Based:</b> Asset (host/user/service/cloud_resource) criticality 1-5, RiskBasedRule conditions_json min_severity/min_criticality, risk_multiplier, calculate_risk_score: base severity map LOW2 MEDIUM5 HIGH8 CRITICAL10 * criticality factor 0.5+crit*0.3 * rule multipliers. Seed Domain Controller 5, Prod DB 5, CEO Laptop 4.</li>
          <li><b>78-79 Purple Team:</b> PurpleTeamExercise MITRE tactic/technique T1059.001/T1078/T1053.005, steps_json action/command/expected_detection, run creates SecurityAlert purple_team, score 85 if detected, PurpleTeamFinding detection_gap if score &lt;70.</li>
          <li><b>80 PDF Export:</b> PDFExport linked ExecReport, s3://noctra-exports/exports/org_id=1/pdf/board_pack_*.pdf, mock 12 pages 250KB, includes_charts true, real impl would use reportlab/weasyprint.</li>
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
                {tab === "datalake" && <><Button size="sm" onClick={async()=>{ const r=await api.dataLakeExport(); setExtra(r.data); }}>Export Alerts</Button><Button variant="secondary" size="sm" onClick={async()=>{ const r=await api.dataLakeQuery("SELECT * FROM security_alerts WHERE org_id=1"); setExtra(r.data); }}>Athena Query</Button></>}
                {tab === "ha" && <Button size="sm" onClick={async()=>{ const r=await api.haNodes(); setExtra(r.data); }}>Nodes</Button>}
              </div>
            </div>

            <div className="text-xs space-y-2">
              {tab === "partition" && <><p>Partitioning: {data?.redis_connected !== undefined ? "HA status" : "Postgres RANGE monthly"} — DB_PARTITIONING_ENABLED flag</p><p className="text-content-tertiary">Creates partitions for current + next 2 months: security_alerts_pYYYYMM etc.</p></>}
              {tab === "datalake" && <><p>Exports: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Parquet path org_id/year/month, Athena mock returns count.</p></>}
              {tab === "ha" && <><p>Messages: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Redis pub/sub + DB fallback, multi-region us-east-1/eu-west-1/ap-south-1</p></>}
              {tab === "marketplace" && <><p>Playbooks: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Seeded 4 verified, install creates local SoarPlaybook.</p></>}
              {tab === "finetune" && <><p>Jobs: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Dataset from cases/alerts, mock training loss 0.12 acc 0.94</p></>}
              {tab === "risk" && <><p>Assets: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Criticality 5=Domain Controller/Prod DB, risk score base*criticality*rule multiplier</p></>}
              {tab === "purple" && <><p>Exercises: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">T1059.001 PowerShell, T1078 Valid Accounts, T1053 Scheduled Task, creates purple_team alerts</p></>}
              {tab === "pdf" && <><p>PDFs: {Array.isArray(data) ? data.length : 0}</p><p className="text-content-tertiary">Board pack PDF 12 pages, s3://noctra-exports, includes charts</p></>}
            </div>

            <pre className="mt-6 p-4 bg-app-subtle rounded text-xs overflow-auto max-h-[400px] border border-line-subtle">{JSON.stringify(data, null, 2)}</pre>
            {extra && <pre className="mt-3 p-4 bg-app-surface border border-accent-primary/30 rounded text-xs overflow-auto max-h-[300px]">{JSON.stringify(extra, null, 2)}</pre>}
          </div>
        )}
      </Card>
    </div>
  );
}
