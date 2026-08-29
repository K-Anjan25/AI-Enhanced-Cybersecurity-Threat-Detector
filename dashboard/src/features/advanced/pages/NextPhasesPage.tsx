import React, { useEffect, useState } from "react";
import { Card, Badge, Button, PageHeader, Spinner } from "../../../components/ui";
import { Shield, Search, Bug, Bot } from "lucide-react";
import { advancedApi } from "../../../api/advancedApi";
import apiClient from "../../../api/client";

const nextApi = {
  ztnaSegments: () => apiClient.get("/ztna/segments"),
  ztnaPolicies: () => apiClient.get("/ztna/policies"),
  ztnaGraph: () => apiClient.get("/ztna/graph"),
  ztnaEvaluate: (src: string, dst: string) => apiClient.post("/ztna/evaluate", { src_ip: src, dst_ip: dst }),
  hunts: () => apiClient.get("/hunts"),
  huntExecute: (query: string) => apiClient.post("/hunts/execute", { query, limit: 20 }),
  vulns: () => apiClient.get("/vulns"),
  vulnRisk: () => apiClient.get("/vulns/risk/summary"),
  aiAgentStatus: () => apiClient.get("/ai-agent/status"),
  aiInvestigate: (caseId: number) => apiClient.post("/ai-agent/investigate", { case_id: caseId }),
};

type Tab = "ztna" | "hunt" | "vuln" | "agent";

export default function NextPhasesPage() {
  const [tab, setTab] = useState<Tab>("ztna");
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
        case "ztna": res = await nextApi.ztnaGraph(); break;
        case "hunt": res = await nextApi.hunts(); break;
        case "vuln": res = await nextApi.vulnRisk(); break;
        case "agent": res = await nextApi.aiAgentStatus(); break;
      }
      setData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(tab); }, [tab]);

  return (
    <div className="space-y-6">
      <PageHeader title="Next Phases 61-63 + AI Agent 70" description="Zero Trust, Threat Hunting Workbench, Vuln Management, and Autonomous AI Analyst v2 with tool use" />
      
      <div className="p-4 bg-accent-primary/10 border border-accent-primary/30 rounded text-sm">
        <div className="font-bold mb-2">My understanding of Autonomous AI Analyst (current + next):</div>
        <ul className="list-disc ml-5 space-y-1 text-xs">
          <li><b>Product loop:</b> Sense (ingest via connectors/Kafka) → Reason (ML + LLM) → Propose (reversible SOAR) → Approve (human) → Report (tamper-evident). You employ an analyst; you don't operate a dashboard.</li>
          <li><b>LLM reasoning:</b> Anthropic Claude via Messages API when LLM_ENABLED + ANTHROPIC_API_KEY set, else deterministic fallback template so demo works end-to-end. Never raises — resilience contract.</li>
          <li><b>Chat grounding:</b> chat_about_case includes recent 10 alerts OCSF summary as connector_context, blast radius nodes, MITRE mapping, confidence. Rate-limited per org:user:case to prevent cost abuse.</li>
          <li><b>Analysis contract:</b> headline, what_happened, why_it_matters, blast_radius_summary, recommended_action [action_type, target, rationale, undo], confidence, model, fallback.</li>
          <li><b>Auto-triage:</b> CRITICAL/HIGH alerts from connectors auto-create analyst cases with OCSF context.</li>
          <li><b>Next evolution (Phase 70):</b> Multi-step agent with tool use — hunt KQL, vuln_risk, ztna_evaluate, threat_intel, attack_heatmap, case_timeline. Memory trace in AgentMemory, tasks in AgentTask, max steps bounded, honest: never auto-executes SOAR unless AI_AGENT_AUTO_APPROVE_LOW_RISK + LOW severity.</li>
        </ul>
        <div className="mt-3 font-bold">Doubts / Need inputs:</div>
        <ul className="list-disc ml-5 space-y-1 text-xs">
          <li>Do you want agent to auto-approve LOW risk? Currently flag false — should we enable for demo?</li>
          <li>LLM tool use: Should we implement full Anthropic tool_use API (beta) or keep prompt-based simulation? Full requires parsing tool_use blocks.</li>
          <li>Memory: Should agent remember across cases (org-level) or per-case only? Current per-case with TTL 24h.</li>
          <li>Hunting: Do you want saved hunts to auto-run on schedule (cron) and create cases when results &gt; threshold?</li>
          <li>ZTNA: Do you have real network segments (CIDRs) to import, or should we seed defaults (10.0.0.0/24 internal, 0.0.0.0/0 external)?</li>
          <li>Vuln: Should we integrate real scanner (Trivy API) or keep mock ingestion? S3 bucket for reports?</li>
          <li>Should AI Agent have a dedicated UI chat (like ChatGPT) with streaming, or keep embedded in case view?</li>
        </ul>
      </div>

      <div className="flex flex-wrap gap-2">
        {[
          { id: "ztna", label: "ZTNA P61", icon: Shield },
          { id: "hunt", label: "Hunting P62", icon: Search },
          { id: "vuln", label: "Vulns P63", icon: Bug },
          { id: "agent", label: "AI Agent P70", icon: Bot },
        ].map(t => {
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
              <Button variant="secondary" size="sm" onClick={() => load(tab)}>Refresh</Button>
            </div>

            {tab === "ztna" && <ZtnaView data={data} extra={extra} setExtra={setExtra} />}
            {tab === "hunt" && <HuntView data={data} setExtra={setExtra} extra={extra} />}
            {tab === "vuln" && <VulnView data={data} />}
            {tab === "agent" && <AgentView data={data} setExtra={setExtra} extra={extra} />}

            <pre className="mt-6 p-4 bg-app-subtle rounded text-xs overflow-auto max-h-[400px] border border-line-subtle">{JSON.stringify(data, null, 2)}</pre>
            {extra && <pre className="mt-3 p-4 bg-app-surface border border-accent-primary/30 rounded text-xs overflow-auto max-h-[300px]">{JSON.stringify(extra, null, 2)}</pre>}
          </div>
        )}
      </Card>
    </div>
  );
}

function ZtnaView({ data, extra, setExtra }: any) {
  const [src, setSrc] = useState("10.0.0.5");
  const [dst, setDst] = useState("10.0.1.10");
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="p-3 bg-app-subtle rounded border">Nodes: {data?.nodes?.length ?? 0} segments</div>
        <div className="p-3 bg-app-subtle rounded border">Edges: {data?.edges?.length ?? 0} policies, default {data?.default_action}</div>
      </div>
      <div className="flex gap-2">
        <input value={src} onChange={e=>setSrc(e.target.value)} className="px-2 py-1 bg-app-subtle border rounded text-xs w-32" placeholder="src ip" />
        <input value={dst} onChange={e=>setDst(e.target.value)} className="px-2 py-1 bg-app-subtle border rounded text-xs w-32" placeholder="dst ip" />
        <Button size="sm" onClick={async()=>{ const r=await nextApi.ztnaEvaluate(src,dst); setExtra(r.data); }}>Evaluate</Button>
      </div>
      <p className="text-xs text-content-tertiary">Phase 61: CIDR validation, segment matching, policy priority eval, decision log, microseg graph for visualization.</p>
    </div>
  );
}
function HuntView({ data, extra, setExtra }: any) {
  const [q, setQ] = useState("severity:CRITICAL AND source:okta");
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input value={q} onChange={e=>setQ(e.target.value)} className="flex-1 px-3 py-2 bg-app-subtle border rounded text-xs" placeholder="KQL query" />
        <Button size="sm" onClick={async()=>{ const r=await nextApi.huntExecute(q); setExtra(r.data); }}>Run Hunt</Button>
      </div>
      <div className="text-xs">Saved hunts: {Array.isArray(data) ? data.length : 0}</div>
      <p className="text-xs text-content-tertiary">Phase 62: KQL subset parser (field:value, AND, free text), translates to SQLAlchemy filters, honest note about OR/NOT partial.</p>
    </div>
  );
}
function VulnView({ data }: any) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-2 text-xs">
        <div className="p-2 bg-app-subtle rounded border">Total: {data?.total_vulns}</div>
        <div className="p-2 bg-red-500/20 rounded border">Critical: {data?.open_by_severity?.critical}</div>
        <div className="p-2 bg-orange-500/20 rounded border">High: {data?.open_by_severity?.high}</div>
        <div className="p-2 bg-app-subtle rounded border">Risk: {data?.risk_score} ({data?.risk_band})</div>
      </div>
      <p className="text-xs text-content-tertiary">Phase 63: Vuln ingestion (Trivy/Nessus), risk scoring CVSS, correlation with alerts, top assets.</p>
    </div>
  );
}
function AgentView({ data, extra, setExtra }: any) {
  const [caseId, setCaseId] = useState("1");
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="p-2 bg-app-subtle rounded border">Enabled: {String(data?.ai_agent_enabled)}</div>
        <div className="p-2 bg-app-subtle rounded border">LLM: {data?.llm_model}</div>
        <div className="p-2 bg-app-subtle rounded border">Tools: {data?.tools?.length}</div>
      </div>
      <div className="flex gap-2">
        <input value={caseId} onChange={e=>setCaseId(e.target.value)} className="px-2 py-1 bg-app-subtle border rounded text-xs w-20" placeholder="case id" />
        <Button size="sm" onClick={async()=>{ const r=await nextApi.aiInvestigate(Number(caseId)); setExtra(r.data); }}>Autonomous Investigate</Button>
      </div>
      <p className="text-xs text-content-tertiary">Phase 70: Agentic loop up to {data?.max_steps} steps, tool registry, memory trace, fallback deterministic if no LLM key. Honest: never auto-executes unless flag + LOW.</p>
    </div>
  );
}

