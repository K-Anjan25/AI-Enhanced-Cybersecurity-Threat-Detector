import React, { useEffect, useState } from "react";
import { Card, Badge, Button, PageHeader, Spinner } from "../../../components/ui";
import { RawData } from "../../../components/ui";
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

export type Tab = "ztna" | "hunt" | "vuln" | "agent";

export default function NextPhasesPage({ initialTab }: { initialTab?: Tab } = {}) {
  const [tab, setTab] = useState<Tab>(initialTab ?? "ztna");
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
      <PageHeader title="Detection & Response Labs" description="Zero trust access, the threat hunting workbench, vulnerability management and the autonomous analyst with tool use." />
      
      <div className="flex flex-wrap gap-2">
        {[
          { id: "ztna", label: "ZTNA", icon: Shield },
          { id: "hunt", label: "Hunting", icon: Search },
          { id: "vuln", label: "Vulns", icon: Bug },
          { id: "agent", label: "AI Agent", icon: Bot },
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

            <RawData value={data} />
            <RawData value={extra} label="Result" />
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
      <p className="text-xs text-content-tertiary">CIDR validation, segment matching, policy priority eval, decision log, microseg graph for visualization.</p>
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
      <p className="text-xs text-content-tertiary">KQL subset parser (field:value, AND, free text), translates to SQLAlchemy filters, honest note about OR/NOT partial.</p>
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
      <p className="text-xs text-content-tertiary">Vuln ingestion (Trivy/Nessus), risk scoring CVSS, correlation with alerts, top assets.</p>
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
      <p className="text-xs text-content-tertiary">Agentic loop up to {data?.max_steps} steps, tool registry, memory trace, fallback deterministic if no LLM key. Honest: never auto-executes unless flag + LOW.</p>
    </div>
  );
}

