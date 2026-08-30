import React, { useEffect, useState } from "react";
import { advancedApi } from "../../../api/advancedApi";
import { Card, Badge, Button, PageHeader, Spinner, RawData } from "../../../components/ui";
import { Shield, Zap, MessageSquare, FileCode, Package, Users, Brain, Map, Archive, Server, Smartphone, CreditCard } from "lucide-react";

type Tab = "threat" | "soar" | "collab" | "sigma" | "compliance" | "teams" | "ml" | "attack" | "retention" | "ha" | "pwa" | "billing";

export default function AdvancedHubPage() {
  const [tab, setTab] = useState<Tab>("threat");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (t: Tab) => {
    setLoading(true);
    setError(null);
    try {
      let res: any;
      switch (t) {
        case "threat": res = await advancedApi.threatIntelStatus(); break;
        case "soar": res = await advancedApi.soarTargets(); break;
        case "collab": res = { data: { note: "Select a case to view comments" } }; break;
        case "sigma": res = await advancedApi.listSigma(); break;
        case "compliance": res = await advancedApi.listPacks(); break;
        case "teams": res = await advancedApi.listTeams(); break;
        case "ml": res = await advancedApi.feedbackStats(); break;
        case "attack": res = await advancedApi.attackHeatmap(); break;
        case "retention": res = await advancedApi.retentionPolicies(); break;
        case "ha": res = await advancedApi.haStatus(); break;
        case "pwa": res = await advancedApi.pwaStatus(); break;
        case "billing": res = await advancedApi.billingUsage(); break;
        default: res = { data: {} };
      }
      setData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(tab); }, [tab]);

  const tabs: { id: Tab; label: string; icon: any }[] = [
    { id: "threat", label: "Threat Intel", icon: Shield },
    { id: "soar", label: "SOAR Exec", icon: Zap },
    { id: "collab", label: "Collaboration", icon: MessageSquare },
    { id: "sigma", label: "Sigma DSL", icon: FileCode },
    { id: "compliance", label: "Compliance Packs", icon: Package },
    { id: "teams", label: "Teams & Invites", icon: Users },
    { id: "ml", label: "ML Feedback", icon: Brain },
    { id: "attack", label: "ATT&CK", icon: Map },
    { id: "retention", label: "Data Lifecycle", icon: Archive },
    { id: "ha", label: "HA Status", icon: Server },
    { id: "pwa", label: "PWA", icon: Smartphone },
    { id: "billing", label: "Billing", icon: CreditCard },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Advanced Hub" description="Threat intel, playbook execution, collaboration, Sigma rules, compliance packs, teams, model feedback, ATT&CK, retention, availability and billing." />
      
      <div className="flex flex-wrap gap-2">
        {tabs.map(t => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-3 py-2 rounded text-xs font-semibold border transition ${tab === t.id ? "bg-accent-primary text-black border-accent-primary" : "bg-app-surface border-line-subtle text-content-secondary hover:border-accent-primary/50"}`}
            >
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
              <h3 className="font-bold text-lg">{tabs.find(t=>t.id===tab)?.label}</h3>
              <Button variant="secondary" size="sm" onClick={() => load(tab)}>Refresh</Button>
            </div>
            
            {tab === "threat" && <ThreatIntelView data={data} />}
            {tab === "soar" && <SoarView data={data} />}
            {tab === "sigma" && <SigmaView data={data} />}
            {tab === "compliance" && <ComplianceView data={data} />}
            {tab === "teams" && <TeamsView data={data} />}
            {tab === "ml" && <MLView data={data} />}
            {tab === "attack" && <AttackView data={data} />}
            {tab === "retention" && <RetentionView data={data} />}
            {tab === "ha" && <HAView data={data} />}
            {tab === "pwa" && <PWAView data={data} />}
            {tab === "billing" && <BillingView data={data} />}
            {tab === "collab" && <CollabView />}
            
            {tab !== "collab" && <RawData value={data} />}
          </div>
        )}
      </Card>
    </div>
  );
}

function ThreatIntelView({ data }: { data: any }) {
  const [ip, setIp] = useState("8.8.8.8");
  const [result, setResult] = useState<any>(null);
  return (
    <div className="space-y-4">
      <div className="flex gap-2 items-center">
        <input value={ip} onChange={e=>setIp(e.target.value)} placeholder="IP / domain / hash" className="px-3 py-2 bg-app-subtle border border-line-subtle rounded text-sm w-64" />
        <Button size="sm" onClick={async()=>{ try{ const r=await advancedApi.enrichIp(ip); setResult(r.data);}catch(e:any){setResult({error:e.message})}}}>Enrich IP</Button>
        <Badge>{data?.enabled ? "Enabled" : "Disabled"}</Badge>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-app-subtle rounded border"><div className="text-xs text-content-tertiary">VT</div><div className="font-bold">{data?.providers?.virustotal?.configured ? "Configured" : "No key (honest)"}</div></div>
        <div className="p-3 bg-app-subtle rounded border"><div className="text-xs text-content-tertiary">AbuseIPDB</div><div className="font-bold">{data?.providers?.abuseipdb?.configured ? "Configured" : "No key"}</div></div>
        <div className="p-3 bg-app-subtle rounded border"><div className="text-xs text-content-tertiary">Shodan</div><div className="font-bold">{data?.providers?.shodan?.configured ? "Configured" : "No key"}</div></div>
        <div className="p-3 bg-app-subtle rounded border"><div className="text-xs text-content-tertiary">OTX</div><div className="font-bold">{data?.providers?.otx?.configured ? "Configured" : "No key"}</div></div>
      </div>
      <RawData value={result} label="Enrichment result" />
      <p className="text-xs text-content-tertiary">Without API keys, enrichment returns not_configured and cache only. Aggregation risk 0-100 from VT malicious*suspicious + AbuseIPDB confidence + Shodan vulns + OTX pulses.</p>
    </div>
  );
}
function SoarView({ data }: { data: any }) {
  const [pending, setPending] = useState<any[]>([]);
  useEffect(()=>{ advancedApi.soarPending().then(r=>setPending(r.data)).catch(()=>{}); },[]);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="p-3 bg-app-subtle rounded border"><div className="text-xs">Slack</div><div className="font-bold">{data?.slack_configured ? "Configured" : "Not configured"}</div></div>
        <div className="p-3 bg-app-subtle rounded border"><div className="text-xs">Jira</div><div className="font-bold">{data?.jira_configured ? "Configured" : "Not configured"}</div></div>
        <div className="p-3 bg-app-subtle rounded border"><div className="text-xs">PagerDuty</div><div className="font-bold">{data?.pagerduty_configured ? "Configured" : "Not configured"}</div></div>
      </div>
      <div><h4 className="font-semibold mb-2">Pending Approvals (CRITICAL/HIGH need approval)</h4>{pending.length===0 ? <p className="text-xs text-content-tertiary">No pending approvals</p> : pending.map((p:any)=><div key={p.action_id} className="p-3 bg-app-subtle rounded border mb-2 flex justify-between"><span>{p.action_type} — {p.severity} — {p.rule_name}</span><Button size="sm" onClick={()=>advancedApi.soarApprove(p.action_id).then(()=>setPending(pending.filter(x=>x.action_id!==p.action_id)))}>Approve & Execute</Button></div>)}</div>
      <p className="text-xs text-content-tertiary">Real webhook execution when SOAR_WEBHOOK_ENABLED + target configured. Dry-run evaluates without side effects. Retry/backoff logged.</p>
    </div>
  );
}
function CollabView() {
  const [caseId, setCaseId] = useState("1");
  const [comments, setComments] = useState<any[]>([]);
  const [content, setContent] = useState("");
  const load = async()=>{ try{ const r=await advancedApi.listComments(Number(caseId)); setComments(r.data);}catch{} };
  return (
    <div className="space-y-4">
      <div className="flex gap-2"><input value={caseId} onChange={e=>setCaseId(e.target.value)} className="px-3 py-2 bg-app-subtle border rounded w-20 text-sm" placeholder="Case ID"/><Button size="sm" onClick={load}>Load Comments</Button></div>
      <div className="space-y-2">{comments.map(c=><div key={c.id} className="p-3 bg-app-subtle rounded border"><div className="text-xs text-content-tertiary">User {c.user_id} — {c.created_at}</div><div className="text-sm">{c.content}</div>{c.mentions?.length>0 && <div className="text-xs text-accent-primary">Mentions: {c.mentions.join(", ")}</div>}</div>)}</div>
      <div className="flex gap-2"><input value={content} onChange={e=>setContent(e.target.value)} placeholder="Add comment with @mentions" className="flex-1 px-3 py-2 bg-app-subtle border rounded text-sm"/><Button size="sm" onClick={async()=>{ await advancedApi.createComment(Number(caseId), content); setContent(""); load(); }}>Post</Button></div>
      <p className="text-xs text-content-tertiary">@mention regex extracts, activity feed published to EventBus, WebSocket ready via /api/v1/stream.</p>
    </div>
  );
}
function SigmaView({ data }: { data: any }) {
  const [yaml, setYaml] = useState("title: Test Rule\ndetection:\n  selection:\n    EventID: 4625\n  condition: selection\nlevel: high");
  const [title, setTitle] = useState("Failed Logon Sigma");
  return (
    <div className="space-y-4">
      <div className="flex gap-2"><input value={title} onChange={e=>setTitle(e.target.value)} className="px-3 py-2 bg-app-subtle border rounded text-sm flex-1" placeholder="Rule title"/><Button size="sm" onClick={async()=>{ await advancedApi.createSigma({title, rule_yaml: yaml, level:"high"}); window.location.reload(); }}>Create Sigma</Button></div>
      <textarea value={yaml} onChange={e=>setYaml(e.target.value)} className="w-full h-40 p-3 bg-app-subtle border rounded text-xs font-mono" />
      <div className="space-y-1">{Array.isArray(data) && data.map((r:any)=><div key={r.id} className="p-2 bg-app-subtle rounded border text-xs"><span className="font-bold">{r.title}</span> — {r.level} — v{r.version} — {r.is_active ? "active" : "inactive"}</div>)}</div>
      <p className="text-xs text-content-tertiary">Sigma YAML parsed (yaml safe_load fallback regex), versioned, DSL with AND/OR/IN/==.</p>
    </div>
  );
}
function ComplianceView({ data }: { data: any }) {
  return (
    <div className="space-y-3">
      {Array.isArray(data) && data.map((p:any)=><div key={p.id} className="p-3 bg-app-subtle rounded border"><div className="font-bold">{p.name} — {p.description}</div><div className="text-xs text-content-tertiary">{p.controls?.length} controls</div><Button size="sm" className="mt-2" onClick={()=>advancedApi.exportPackS3(p.name)}>Export to S3</Button></div>)}
      <p className="text-xs text-content-tertiary">ISO27001/NIST/GDPR/SOC2 packs with controls JSON. S3 export via boto3 if configured else local fallback.</p>
    </div>
  );
}
function TeamsView({ data }: { data: any }) {
  const [teamName, setTeamName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  return (
    <div className="space-y-4">
      <div className="flex gap-2"><input value={teamName} onChange={e=>setTeamName(e.target.value)} placeholder="Team name" className="px-3 py-2 bg-app-subtle border rounded text-sm"/><Button size="sm" onClick={async()=>{ await advancedApi.createTeam({name: teamName}); setTeamName(""); }}>Create Team</Button></div>
      <div className="flex gap-2"><input value={inviteEmail} onChange={e=>setInviteEmail(e.target.value)} placeholder="Invite email" className="px-3 py-2 bg-app-subtle border rounded text-sm"/><Button size="sm" onClick={async()=>{ await advancedApi.createInvite({email: inviteEmail}); setInviteEmail(""); }}>Invite</Button></div>
      <div>{Array.isArray(data) && data.map((t:any)=><div key={t.id} className="p-2 bg-app-subtle rounded border text-sm">{t.name} — {t.member_count} members</div>)}</div>
      <p className="text-xs text-content-tertiary">Teams + TeamMembership + OrgInvite with token expiry 72h, seat limit MAX_USERS_PER_ORG.</p>
    </div>
  );
}
function MLView({ data }: { data: any }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3"><div className="p-3 bg-app-subtle rounded border"><div className="text-xs">Precision</div><div className="font-bold text-lg">{data?.precision ? (data.precision*100).toFixed(1)+"%" : "N/A"}</div></div><div className="p-3 bg-app-subtle rounded border"><div className="text-xs">Total Feedback</div><div className="font-bold text-lg">{data?.total ?? 0}</div></div><div className="p-3 bg-app-subtle rounded border"><div className="text-xs">FP Rate</div><div className="font-bold text-lg">{data?.false_positive_rate ? (data.false_positive_rate*100).toFixed(1)+"%" : "0%"}</div></div></div>
      <p className="text-xs text-content-tertiary">Feedback types true/false positive, drift detection critical ratio &gt;0.3, model versions.</p>
    </div>
  );
}
function AttackView({ data }: { data: any }) {
  const [matrix, setMatrix] = useState<any>(null);
  useEffect(()=>{ advancedApi.attackMatrix().then(r=>setMatrix(r.data)).catch(()=>{}); },[]);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-6 gap-2">{data?.heatmap?.slice(0,12).map((h:any)=><div key={h.technique_id} className="p-2 bg-app-subtle rounded border text-xs"><div className="font-bold">{h.technique_id}</div><div>{h.count} hits</div></div>)}</div>
      {matrix && <div className="text-xs"><div className="font-bold mb-2">ATT&CK Matrix — {matrix.tactics?.length} tactics</div><div className="flex flex-wrap gap-1">{matrix.tactics?.map((t:any)=><span key={t.id} className="px-2 py-1 bg-app-subtle rounded border">{t.name}</span>)}</div></div>}
      <p className="text-xs text-content-tertiary">Heatmap aggregates SecurityAlert.mitre_technique_id, ATT&CK navigator layer export, actor attribution via overlap scoring.</p>
    </div>
  );
}
function RetentionView({ data }: { data: any }) {
  const [archive, setArchive] = useState<any>(null);
  return (
    <div className="space-y-3">
      {Array.isArray(data) && data.map((p:any)=><div key={p.id} className="p-3 bg-app-subtle rounded border text-sm"><div className="font-bold">{p.data_type} — {p.retention_days}d retain / {p.archive_after_days}d archive / {p.delete_after_days}d delete</div><div className="text-xs text-content-tertiary">{p.description}</div></div>)}
      <Button size="sm" onClick={() => { void advancedApi.runArchive(true).then((r) => setArchive(r.data)).catch((e) => setArchive({ error: e?.message ?? "Dry-run failed" })); }}>Dry-run Archive</Button>
      <RawData value={archive} label="Dry-run result" />
      <p className="text-xs text-content-tertiary">Retention policies (alerts 90/60/90), legal hold prevents archival, GDPR anonymization.</p>
    </div>
  );
}
function HAView({ data }: { data: any }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 bg-app-subtle rounded border"><div className="text-xs">Redis</div><div className="font-bold">{data?.redis_available ? "Available" : "Not available (honest)"}</div></div>
        <div className="p-3 bg-app-subtle rounded border"><div className="text-xs">EventBus</div><div className="font-bold">{data?.eventbus_backend}</div></div>
      </div>
      <div className="text-xs space-y-1">
        <div>Honest gaps:</div>
        <ul className="list-disc ml-4">
          {data?.honest_gaps?.map((g:string,i:number)=><li key={i}>{g}</li>)}
        </ul>
      </div>
      <p className="text-xs text-content-tertiary">RedisEventBus publish, distributed lock SETNX, HA status endpoint. RLS not enabled — org_id filter instead.</p>
    </div>
  );
}
function PWAView({ data }: { data: any }) {
  return (
    <div className="space-y-3">
      <div className="p-3 bg-app-subtle rounded border"><div className="font-bold">{data?.manifest?.name}</div><div className="text-xs">{data?.manifest?.description}</div><div className="text-xs">Push subs: {data?.push_subscriptions}</div></div>
      <p className="text-xs text-content-tertiary">Manifest + service worker + push via Web Push API (VAPID). Offline queue client-side IndexedDB.</p>
      <Button size="sm" onClick={()=>{ if('serviceWorker' in navigator){ navigator.serviceWorker.register('/sw.js').then(()=>alert('SW registered')).catch(e=>alert(e.message)); }}}>Register SW</Button>
    </div>
  );
}
function BillingView({ data }: { data: any }) {
  const [plans, setPlans] = useState<any[]>([]);
  useEffect(()=>{ advancedApi.billingPlans().then(r=>setPlans(r.data)).catch(()=>{}); },[]);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3"><div className="p-3 bg-app-subtle rounded border"><div className="text-xs">Alerts</div><div className="font-bold">{data?.alerts_ingested} / {data?.quota?.max_alerts_per_month}</div><div className="text-xs">{data?.usage_percent?.alerts?.toFixed(1)}%</div></div><div className="p-3 bg-app-subtle rounded border"><div className="text-xs">Cases</div><div className="font-bold">{data?.cases_created} / {data?.quota?.max_cases_per_month}</div></div><div className="p-3 bg-app-subtle rounded border"><div className="text-xs">Users</div><div className="font-bold">{data?.users_active} / {data?.quota?.max_users}</div></div></div>
      <div className="flex gap-2">{plans.map((p:any)=><div key={p.id} className="p-3 bg-app-subtle rounded border text-xs"><div className="font-bold">{p.name} — ${p.price_per_month}/mo</div><div>{p.max_alerts} alerts, {p.max_users} users</div></div>)}</div>
      <p className="text-xs text-content-tertiary">Usage metering per org per month, quota enforcement 429 when exceeded, free/pro/enterprise plans.</p>
    </div>
  );
}
