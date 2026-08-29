import { useEffect, useState } from "react";
import apiClient from "../../../api/client";

const api = apiClient;
const useToast = () => ({ push: (o:any)=> console.log(o.title) });

export default function Final10Page() {
  const { push } = useToast();
  const [tab, setTab] = useState<"intel"|"quantum"|"attack"|"cart"|"fabric"|"socmgr"|"drp"|"cnapp"|"posture"|"noctra">("noctra");
  const [intel, setIntel] = useState<any[]>([]);
  const [quantum, setQuantum] = useState<any[]>([]);
  const [paths, setPaths] = useState<any[]>([]);
  const [cartJobs, setCartJobs] = useState<any[]>([]);
  const [sources, setSources] = useState<any[]>([]);
  const [query, setQuery] = useState("SELECT * FROM alerts WHERE severity='HIGH' LIMIT 100");
  const [queryRes, setQueryRes] = useState<any>(null);
  const [dashboard, setDashboard] = useState<any>(null);
  const [orchestrations, setOrchestrations] = useState<any[]>([]);
  const [monitors, setMonitors] = useState<any[]>([]);
  const [drpFindings, setDrpFindings] = useState<any[]>([]);
  const [clusters, setClusters] = useState<any[]>([]);
  const [workloads, setWorkloads] = useState<any[]>([]);
  const [cnappSummary, setCnappSummary] = useState<any>(null);
  const [posture, setPosture] = useState<any>(null);
  const [postureRecs, setPostureRecs] = useState<any[]>([]);
  const [osConfig, setOsConfig] = useState<any>(null);
  const [osMetrics, setOsMetrics] = useState<any>(null);
  const [osLogs, setOsLogs] = useState<any[]>([]);

  const load = async () => {
    try {
      const [i, q, p, cj, src, dash, orchs, mons, drpf, cl, wl, sum, post, recs, cfg, mets, logs] = await Promise.allSettled([
        api.get("/federated-intel/"),
        api.get("/quantum-safe/inventory"),
        api.get("/attack-path/"),
        api.get("/cart/jobs"),
        api.get("/data-fabric/sources"),
        api.get("/soc-manager/dashboard"),
        api.get("/soc-manager/orchestrations"),
        api.get("/drp/monitors"),
        api.get("/drp/findings"),
        api.get("/cnapp/clusters"),
        api.get("/cnapp/workloads"),
        api.get("/cnapp/summary"),
        api.get("/posture-score/latest"),
        api.get("/posture-score/recommendations"),
        api.get("/noctra-os/config"),
        api.get("/noctra-os/metrics"),
        api.get("/noctra-os/logs"),
      ]);
      if (i.status==="fulfilled") setIntel(i.value.data || []);
      if (q.status==="fulfilled") setQuantum(q.value.data || []);
      if (p.status==="fulfilled") setPaths(p.value.data || []);
      if (cj.status==="fulfilled") setCartJobs(cj.value.data || []);
      if (src.status==="fulfilled") setSources(src.value.data || []);
      if (dash.status==="fulfilled") setDashboard(dash.value.data || null);
      if (orchs.status==="fulfilled") setOrchestrations(orchs.value.data || []);
      if (mons.status==="fulfilled") setMonitors(mons.value.data || []);
      if (drpf.status==="fulfilled") setDrpFindings(drpf.value.data || []);
      if (cl.status==="fulfilled") setClusters(cl.value.data || []);
      if (wl.status==="fulfilled") setWorkloads(wl.value.data || []);
      if (sum.status==="fulfilled") setCnappSummary(sum.value.data || null);
      if (post.status==="fulfilled") setPosture(post.value.data || null);
      if (recs.status==="fulfilled") setPostureRecs(recs.value.data || []);
      if (cfg.status==="fulfilled") setOsConfig(cfg.value.data || null);
      if (mets.status==="fulfilled") setOsMetrics(mets.value.data || null);
      if (logs.status==="fulfilled") setOsLogs(logs.value.data || []);
    } catch {}
  };

  useEffect(() => { load(); }, []);

  const createIntel = async () => {
    try {
      await api.post("/federated-intel/", { name: `Intel-${Date.now()}`, stix_bundle: { type: "bundle", objects: [{ type: "indicator", pattern: "[file:hashes.MD5 = 'abc']" }] }, tlp: "AMBER", is_anonymized: true });
      push({ title: "Shared STIX bundle TLP AMBER anonymized" });
      load();
    } catch (e:any) { push({ title: e.response?.data?.detail || "Error" }); }
  };

  const scanQuantum = async () => {
    try {
      const res = await api.post("/quantum-safe/scan");
      setQuantum(res.data || []);
      push({ title: `Scanned ${res.data?.length||0} crypto inventory` });
    } catch (e:any) { push({ title: e.response?.data?.detail || "Error" }); }
  };

  const analyzePaths = async () => {
    try {
      const res = await api.post("/attack-path/analyze");
      setPaths(res.data || []);
      push({ title: `Found ${res.data?.length||0} attack paths` });
    } catch (e:any) { push({ title: e.response?.data?.detail || "Error" }); }
  };

  const createCart = async () => {
    try {
      await api.post("/cart/jobs", { name: `CART-${Date.now()}`, schedule_cron: "0 2 * * *", config: { techniques: ["T1078","T1021","T1059"] } });
      push({ title: "CART job created" });
      load();
    } catch (e:any) { push({ title: e.response?.data?.detail || "Error" }); }
  };

  const runCart = async (id:number) => {
    try {
      await api.post(`/cart/jobs/${id}/run`);
      push({ title: `CART job ${id} executed` });
      load();
    } catch (e:any) { push({ title: e.response?.data?.detail || "Error" }); }
  };

  const runQuery = async () => {
    try {
      const res = await api.post("/data-fabric/query", { query });
      setQueryRes(res.data);
      push({ title: `Query returned ${res.data?.result_count||0} rows` });
    } catch (e:any) { push({ title: e.response?.data?.detail || "Error" }); }
  };

  const orchestrate = async (caseId:number) => {
    try {
      await api.post("/soc-manager/orchestrate", { case_id: caseId });
      push({ title: `Orchestrated case ${caseId}` });
      load();
    } catch (e:any) { push({ title: e.response?.data?.detail || "Error" }); }
  };

  const scanDrp = async () => {
    try {
      const res = await api.post("/drp/scan");
      setDrpFindings(res.data || []);
      push({ title: `DRP scan found ${res.data?.length||0}` });
    } catch (e:any) { push({ title: e.response?.data?.detail || "Error" }); }
  };

  const calcPosture = async () => {
    try {
      const res = await api.get("/posture-score/latest");
      setPosture(res.data);
      push({ title: `Posture ${res.data?.overall_score?.toFixed(1)}` });
    } catch (e:any) { push({ title: e.response?.data?.detail || "Error" }); }
  };

  const setAutonomy = async (level:string) => {
    try {
      const res = await api.post("/noctra-os/autonomy", { autonomy_level: level });
      setOsConfig(res.data);
      push({ title: `Autonomy set to ${level}` });
      load();
    } catch (e:any) { push({ title: e.response?.data?.detail || "Error" }); }
  };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-bold">Final 10 — P91 to P100 NOCTRA OS</h1>
      <div className="flex gap-2 flex-wrap">
        {[
          ["intel","P91 Intel Share"],
          ["quantum","P92 Quantum-Safe"],
          ["attack","P93 Attack Path"],
          ["cart","P94 CART"],
          ["fabric","P95 Data Fabric"],
          ["socmgr","P96 SOC Mgr"],
          ["drp","P97 DRP"],
          ["cnapp","P98 CNAPP"],
          ["posture","P99 Posture v2"],
          ["noctra","P100 NOCTRA OS"],
        ].map(([k,label])=>(
          <button key={k} onClick={()=>setTab(k as any)} className={`px-3 py-1 rounded border text-sm ${tab===k?'bg-violet-600 text-white border-violet-600':'bg-white'}`}>{label}</button>
        ))}
      </div>

      {tab==="intel" && (
        <div className="space-y-3">
          <div className="flex gap-2"><button onClick={createIntel} className="px-3 py-1 bg-indigo-600 text-white rounded">Share STIX Bundle TLP AMBER Anonymized</button></div>
          <div className="grid gap-2">
            {intel.map((p:any)=>(<div key={p.id} className="border p-3 rounded bg-white"><div className="font-medium">{p.name}</div><div className="text-xs">TLP {p.tlp} anon {String(p.is_anonymized)} status {p.status}</div></div>))}
          </div>
        </div>
      )}

      {tab==="quantum" && (
        <div className="space-y-3">
          <div className="flex gap-2"><button onClick={scanQuantum} className="px-3 py-1 bg-indigo-600 text-white rounded">Scan Crypto Inventory</button></div>
          <div className="grid gap-2">
            {quantum.map((c:any)=>(<div key={c.id} className="border p-3 rounded bg-white"><div className="font-medium">{c.algorithm} {c.key_size} {c.usage}</div><div className="text-xs">quantum_safe {String(c.is_quantum_safe)} risk {c.risk_score} status {c.migration_status}</div></div>))}
          </div>
        </div>
      )}

      {tab==="attack" && (
        <div className="space-y-3">
          <div className="flex gap-2"><button onClick={analyzePaths} className="px-3 py-1 bg-indigo-600 text-white rounded">Analyze Attack Paths</button></div>
          <div className="grid gap-2">
            {paths.map((p:any)=>(<div key={p.id} className="border p-3 rounded bg-white"><div className="font-medium">Risk {p.risk_score} {p.path_type} crown_jewel {p.crown_jewel_asset_id}</div><pre className="text-xs overflow-auto max-h-40">{JSON.stringify(p.path, null, 2)}</pre><div className="text-xs">Choke {p.choke_point_asset_id} Exposure {p.exposure_asset_id}</div></div>))}
          </div>
        </div>
      )}

      {tab==="cart" && (
        <div className="space-y-3">
          <div className="flex gap-2"><button onClick={createCart} className="px-3 py-1 bg-indigo-600 text-white rounded">Create CART Job</button></div>
          <div className="grid gap-2">
            {cartJobs.map((j:any)=>(<div key={j.id} className="border p-3 rounded bg-white flex justify-between"><div><div className="font-medium">{j.name} cron {j.schedule_cron}</div><div className="text-xs">scheduled {String(j.is_scheduled)}</div></div><button onClick={()=>runCart(j.id)} className="px-2 py-1 bg-orange-600 text-white rounded text-xs">Run (detect T1078 gap)</button></div>))}
          </div>
        </div>
      )}

      {tab==="fabric" && (
        <div className="space-y-3">
          <div className="border p-3 rounded bg-white space-y-2">
            <div className="font-medium">Sources: {sources.map((s:any)=>`${s.name}(${s.source_type})`).join(", ")}</div>
            <textarea value={query} onChange={e=>setQuery(e.target.value)} className="w-full border p-2 rounded text-xs h-24" />
            <button onClick={runQuery} className="px-3 py-1 bg-indigo-600 text-white rounded">Run Unified Query</button>
            {queryRes && <pre className="text-xs bg-gray-50 p-2 rounded max-h-60 overflow-auto">{JSON.stringify(queryRes, null, 2)}</pre>}
          </div>
        </div>
      )}

      {tab==="socmgr" && (
        <div className="space-y-3">
          <div className="border p-3 rounded bg-white">
            <div className="font-bold">SOC Manager Dashboard</div>
            {dashboard && <pre className="text-xs">{JSON.stringify(dashboard.agents, null, 2)}</pre>}
          </div>
          <div className="flex gap-2"><input id="caseId" placeholder="case_id" className="border p-1 rounded" /><button onClick={()=>{const el=document.getElementById('caseId') as HTMLInputElement; if(el) orchestrate(Number(el.value));}} className="px-3 py-1 bg-indigo-600 text-white rounded">Orchestrate Case (hunter/enricher/responder consensus)</button></div>
          <div className="grid gap-2">{orchestrations.map((o:any)=>(<div key={o.id} className="border p-2 rounded bg-white text-xs"><div>Case {o.case_id} status {o.status}</div><pre className="max-h-40 overflow-auto">{JSON.stringify(o.workflow, null, 2)}</pre></div>))}</div>
        </div>
      )}

      {tab==="drp" && (
        <div className="space-y-3">
          <div className="flex gap-2"><button onClick={scanDrp} className="px-3 py-1 bg-indigo-600 text-white rounded">Scan Dark Web (leaked_credential/brand_impersonation)</button></div>
          <div className="text-xs">Monitors: {monitors.map((m:any)=>`${m.name}(${m.monitor_type}:${m.keyword})`).join(", ")}</div>
          <div className="grid gap-2">{drpFindings.map((f:any)=>(<div key={f.id} className="border p-3 rounded bg-white"><div className="font-medium">{f.title} [{f.severity}] {f.finding_type}</div><div className="text-xs">{f.description} source {f.source}</div><pre className="text-xs bg-gray-50 p-1 rounded">{JSON.stringify(f.evidence, null, 2)}</pre></div>))}</div>
        </div>
      )}

      {tab==="cnapp" && (
        <div className="space-y-3">
          {cnappSummary && <div className="border p-3 rounded bg-white text-xs">Summary: {JSON.stringify(cnappSummary)}</div>}
          <div className="grid grid-cols-2 gap-2">
            <div className="border p-3 rounded bg-white"><div className="font-medium">Clusters</div>{clusters.map((c:any)=>(<div key={c.id} className="text-xs">{c.name} {c.provider} {c.region} nodes {c.node_count}</div>))}</div>
            <div className="border p-3 rounded bg-white"><div className="font-medium">Workloads</div>{workloads.map((w:any)=>(<div key={w.id} className="text-xs">{w.name} ns:{w.namespace} img:{w.image} priv:{String(w.is_privileged)} risk:{w.risk_score}</div>))}</div>
          </div>
        </div>
      )}

      {tab==="posture" && (
        <div className="space-y-3">
          <div className="flex gap-2"><button onClick={calcPosture} className="px-3 py-1 bg-indigo-600 text-white rounded">Recalculate Posture v2</button></div>
          {posture && <div className="border p-3 rounded bg-white"><div className="font-bold">Overall {posture.overall_score?.toFixed(1)} trend {posture.trend} prev {posture.previous_score}</div><pre className="text-xs">{JSON.stringify(posture.breakdown, null, 2)}</pre><pre className="text-xs">{JSON.stringify(posture.business_context, null, 2)}</pre></div>}
          <div className="border p-3 rounded bg-white"><div className="font-medium">Recommendations ROI</div>{postureRecs.map((r:any)=>(<div key={r.id} className="text-xs">{r.title} priority {r.priority} effort {r.effort} impact {r.impact_score} cost ${r.estimated_cost} benefit ${r.estimated_benefit}</div>))}</div>
        </div>
      )}

      {tab==="noctra" && (
        <div className="space-y-3">
          {osConfig && <div className="border p-3 rounded bg-white"><div className="font-bold text-lg">NOCTRA OS {osConfig.autonomy_level}</div><div className="text-xs">Modules {osConfig.modules?.length} enabled: {osConfig.modules?.slice(0,10).join(", ")}...</div><div className="text-xs">Policies {JSON.stringify(osConfig.policies)}</div></div>}
          {osMetrics && <div className="border p-3 rounded bg-white text-xs"><div className="font-medium">Metrics</div><pre>{JSON.stringify(osMetrics, null, 2)}</pre></div>}
          <div className="flex gap-2 flex-wrap">
            {["manual","supervised","autonomous","fully_autonomous"].map(l=><button key={l} onClick={()=>setAutonomy(l)} className="px-3 py-1 bg-violet-600 text-white rounded text-xs">{l}</button>)}
          </div>
          <div className="border p-3 rounded bg-white"><div className="font-medium">Decision Trace Logs</div>{osLogs.map((lg:any)=>(<div key={lg.id} className="text-xs border-b py-1">{lg.title} {lg.log_type} {lg.created_at}<pre className="bg-gray-50">{JSON.stringify(lg.decision, null, 2)}</pre></div>))}</div>
          <div className="border p-4 rounded bg-gradient-to-r from-violet-900 to-indigo-900 text-white">
            <div className="text-xl font-bold">NOCTRA OS - Autonomous SOC OS</div>
            <div className="text-sm mt-2">Autonomy Level: supervised/autonomous | Modules: P49-P99 integrated | Policies: auto_triage/contain/remediate | Auto triage, contain, ROI-driven recommendations</div>
            <div className="text-xs mt-2">This is Phase 100 culmination - the OS that orchestrates all 99 previous phases as modules.</div>
          </div>
        </div>
      )}
    </div>
  );
}
