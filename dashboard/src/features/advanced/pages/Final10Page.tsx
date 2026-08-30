import { useCallback, useEffect, useState } from "react";
import {
  ShieldAlert,
  Bot,
  Network,
  Globe,
  Boxes,
  Swords,
  Database,
  Users,
  Share2,
  KeyRound,
  RefreshCw,
} from "lucide-react";
import apiClient from "../../../api/client";
import { Card, PageHeader, Button, Spinner, EmptyState, Badge, SeverityBadge, StatCard } from "../../../components/ui";
import { useToast } from "../../../components/ui/Toast";

/**
 * Security Operations — the capability surfaces that sit around the analyst
 * loop: posture, autonomy, attack paths, external exposure, cloud, adversary
 * emulation, unified search, work routing, intel sharing and crypto readiness.
 *
 * Presented as capabilities, not build phases: the operator does not care which
 * iteration shipped a feature, only what it tells them and what to do next.
 */

type TabId =
  | "posture"
  | "autonomy"
  | "paths"
  | "external"
  | "cloud"
  | "redteam"
  | "search"
  | "routing"
  | "sharing"
  | "crypto";

interface TabDef {
  id: TabId;
  label: string;
  icon: typeof ShieldAlert;
  blurb: string;
}

const TABS: TabDef[] = [
  { id: "posture", label: "Posture score", icon: ShieldAlert, blurb: "One 0–100 number for how well defended you are, and what is dragging it down." },
  { id: "autonomy", label: "Autonomy control", icon: Bot, blurb: "How much NOCTRA is allowed to do on its own, and the decisions it logged." },
  { id: "paths", label: "Attack paths", icon: Network, blurb: "How an attacker would reach your most important systems, and where to break the chain." },
  { id: "external", label: "Brand & dark web", icon: Globe, blurb: "Lookalike domains, leaked credentials and brand abuse found outside your network." },
  { id: "cloud", label: "Cloud & containers", icon: Boxes, blurb: "Clusters and workloads, their images, privileges and risk." },
  { id: "redteam", label: "Continuous red team", icon: Swords, blurb: "Scheduled attack emulation that proves whether your detections actually fire." },
  { id: "search", label: "Unified search", icon: Database, blurb: "One query across every connected source instead of five consoles." },
  { id: "routing", label: "Work routing", icon: Users, blurb: "Who — human or agent — picks up each case, and how loaded they are." },
  { id: "sharing", label: "Intel sharing", icon: Share2, blurb: "Share indicators with trusted peers without leaking customer data." },
  { id: "crypto", label: "Crypto readiness", icon: KeyRound, blurb: "Where you still rely on encryption that quantum computers will eventually break." },
];

const Panel: React.FC<{ title: string; hint?: string; children: React.ReactNode; action?: React.ReactNode }> = ({
  title,
  hint,
  children,
  action,
}) => (
  <Card className="p-5 space-y-3">
    <div className="flex items-start justify-between gap-3">
      <div>
        <h3 className="text-sm font-semibold text-content-primary">{title}</h3>
        {hint && <p className="text-xs text-content-tertiary mt-0.5">{hint}</p>}
      </div>
      {action}
    </div>
    {children}
  </Card>
);

const Row: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="border border-line-subtle rounded-sm p-3 bg-app-subtle/40 text-xs text-content-secondary space-y-1">
    {children}
  </div>
);

const Json: React.FC<{ value: unknown }> = ({ value }) => (
  <pre className="text-[11px] font-mono bg-app-subtle border border-line-subtle rounded-sm p-2 overflow-auto max-h-48 text-content-secondary">
    {JSON.stringify(value, null, 2)}
  </pre>
);

export default function Final10Page() {
  const { push } = useToast();
  const [tab, setTab] = useState<TabId>("posture");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const [intel, setIntel] = useState<any[]>([]);
  const [crypto, setCrypto] = useState<any[]>([]);
  const [paths, setPaths] = useState<any[]>([]);
  const [cartJobs, setCartJobs] = useState<any[]>([]);
  const [sources, setSources] = useState<any[]>([]);
  const [query, setQuery] = useState("SELECT * FROM alerts WHERE severity = 'HIGH' LIMIT 100");
  const [queryRes, setQueryRes] = useState<any>(null);
  const [dashboard, setDashboard] = useState<any>(null);
  const [orchestrations, setOrchestrations] = useState<any[]>([]);
  const [caseId, setCaseId] = useState("");
  const [monitors, setMonitors] = useState<any[]>([]);
  const [drpFindings, setDrpFindings] = useState<any[]>([]);
  const [clusters, setClusters] = useState<any[]>([]);
  const [workloads, setWorkloads] = useState<any[]>([]);
  const [cloudSummary, setCloudSummary] = useState<any>(null);
  const [posture, setPosture] = useState<any>(null);
  const [postureRecs, setPostureRecs] = useState<any[]>([]);
  const [osConfig, setOsConfig] = useState<any>(null);
  const [osMetrics, setOsMetrics] = useState<any>(null);
  const [osLogs, setOsLogs] = useState<any[]>([]);

  const asList = (v: any): any[] => (Array.isArray(v) ? v : []);
  const asObject = (v: any): any => (v && typeof v === "object" && !Array.isArray(v) && v.status !== "error" ? v : null);

  const load = useCallback(async () => {
    setLoading(true);
    const calls: [string, Promise<any>][] = [
      ["intel", apiClient.get("/federated-intel/")],
      ["crypto", apiClient.get("/quantum-safe/inventory")],
      ["paths", apiClient.get("/attack-path/")],
      ["cart", apiClient.get("/cart/jobs")],
      ["sources", apiClient.get("/data-fabric/sources")],
      ["dashboard", apiClient.get("/soc-manager/dashboard")],
      ["orchestrations", apiClient.get("/soc-manager/orchestrations")],
      ["monitors", apiClient.get("/drp/monitors")],
      ["drpFindings", apiClient.get("/drp/findings")],
      ["clusters", apiClient.get("/cnapp/clusters")],
      ["workloads", apiClient.get("/cnapp/workloads")],
      ["cloudSummary", apiClient.get("/cnapp/summary")],
      ["posture", apiClient.get("/posture-score/latest")],
      ["postureRecs", apiClient.get("/posture-score/recommendations")],
      ["osConfig", apiClient.get("/noctra-os/config")],
      ["osMetrics", apiClient.get("/noctra-os/metrics")],
      ["osLogs", apiClient.get("/noctra-os/logs")],
    ];
    const settled = await Promise.allSettled(calls.map(([, p]) => p));
    const value = (key: string): any => {
      const idx = calls.findIndex(([k]) => k === key);
      const r = settled[idx];
      return r && r.status === "fulfilled" ? r.value.data : null;
    };

    setIntel(asList(value("intel")));
    setCrypto(asList(value("crypto")));
    setPaths(asList(value("paths")));
    setCartJobs(asList(value("cart")));
    setSources(asList(value("sources")));
    setDashboard(asObject(value("dashboard")));
    setOrchestrations(asList(value("orchestrations")));
    setMonitors(asList(value("monitors")));
    setDrpFindings(asList(value("drpFindings")));
    setClusters(asList(value("clusters")));
    setWorkloads(asList(value("workloads")));
    setCloudSummary(asObject(value("cloudSummary")));
    setPosture(asObject(value("posture")));
    setPostureRecs(asList(value("postureRecs")));
    setOsConfig(asObject(value("osConfig")));
    setOsMetrics(asObject(value("osMetrics")));
    setOsLogs(asList(value("osLogs")));
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try {
      await fn();
    } catch (e: any) {
      push(e?.response?.data?.detail || e?.message || "Request failed", "error");
    } finally {
      setBusy(null);
    }
  };

  const shareIntel = () =>
    run("intel", async () => {
      await apiClient.post("/federated-intel/", {
        name: `Shared indicators ${new Date().toISOString().slice(0, 16)}`,
        stix_bundle: { type: "bundle", objects: [{ type: "indicator", pattern: "[file:hashes.MD5 = 'abc']" }] },
        tlp: "AMBER",
        is_anonymized: true,
      });
      push("Indicators packaged and shared (anonymised, TLP:AMBER)");
      await load();
    });

  const scanCrypto = () =>
    run("crypto", async () => {
      const res = await apiClient.post("/quantum-safe/scan");
      setCrypto(asList(res.data));
      push(`Inventoried ${asList(res.data).length} places encryption is used`);
    });

  const analyzePaths = () =>
    run("paths", async () => {
      const res = await apiClient.post("/attack-path/analyze");
      setPaths(asList(res.data));
      push(`${asList(res.data).length} attack path(s) mapped`);
    });

  const createRedTeamJob = () =>
    run("cart-create", async () => {
      await apiClient.post("/cart/jobs", {
        name: `Nightly emulation ${new Date().toISOString().slice(0, 10)}`,
        schedule_cron: "0 2 * * *",
        config: { techniques: ["T1078", "T1021", "T1059"] },
      });
      push("Emulation scheduled for 02:00 daily");
      await load();
    });

  const runRedTeamJob = (id: number) =>
    run(`cart-${id}`, async () => {
      await apiClient.post(`/cart/jobs/${id}/run`);
      push("Emulation finished — detection gaps recorded");
      await load();
    });

  const runQuery = () =>
    run("query", async () => {
      const res = await apiClient.post("/data-fabric/query", { query });
      setQueryRes(res.data);
      push(`Query returned ${res.data?.result_count ?? 0} row(s)`);
    });

  const orchestrate = () =>
    run("orchestrate", async () => {
      const id = Number(caseId);
      if (!Number.isFinite(id) || id <= 0) {
        push("Enter a valid case number", "warning");
        return;
      }
      await apiClient.post("/soc-manager/orchestrate", { case_id: id });
      push(`Case ${id} routed`);
      await load();
    });

  const scanExternal = () =>
    run("drp", async () => {
      const res = await apiClient.post("/drp/scan");
      setDrpFindings(asList(res.data));
      push(`External scan found ${asList(res.data).length} item(s)`);
    });

  const recalcPosture = () =>
    run("posture", async () => {
      const res = await apiClient.get("/posture-score/latest");
      setPosture(asObject(res.data));
      push("Posture recalculated");
    });

  const setAutonomy = (level: string) =>
    run(`autonomy-${level}`, async () => {
      const res = await apiClient.post("/noctra-os/autonomy", { autonomy_level: level });
      setOsConfig(asObject(res.data));
      push(`Autonomy set to ${level.replace(/_/g, " ")}`);
      await load();
    });

  const active = TABS.find((t) => t.id === tab)!;

  const scoreTone = (score?: number): "success" | "warning" | "critical" | "default" => {
    if (typeof score !== "number") return "default";
    if (score >= 80) return "success";
    if (score >= 60) return "warning";
    return "critical";
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Security operations"
        description="Posture, autonomy, exposure and assurance surfaces around the analyst loop."
        actions={
          <Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading}>
            <RefreshCw size={13} className="mr-1.5" /> Refresh
          </Button>
        }
      />

      <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Security operations areas">
        {TABS.map((t) => {
          const Icon = t.icon;
          const isActive = tab === t.id;
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-sm text-xs font-semibold border transition ${
                isActive
                  ? "bg-accent-primary text-brand-ink border-accent-primary"
                  : "bg-app-surface border-line-subtle text-content-secondary hover:border-accent-primary/50 hover:text-content-primary"
              }`}
            >
              <Icon size={13} aria-hidden /> {t.label}
            </button>
          );
        })}
      </div>

      <p className="text-sm text-content-secondary">{active.blurb}</p>

      {loading ? (
        <Card className="p-16 flex justify-center">
          <Spinner label="Loading security operations" />
        </Card>
      ) : (
        <div className="space-y-4">
          {tab === "posture" && (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                <StatCard
                  label="Overall posture"
                  value={typeof posture?.overall_score === "number" ? posture.overall_score.toFixed(0) : "—"}
                  hint={posture?.trend ? `Trend: ${posture.trend}` : "No score recorded yet"}
                  tone={scoreTone(posture?.overall_score)}
                  icon={<ShieldAlert size={16} />}
                />
                <StatCard
                  label="Previous score"
                  value={typeof posture?.previous_score === "number" ? posture.previous_score.toFixed(0) : "—"}
                  hint="Last recorded measurement"
                />
                <StatCard label="Open recommendations" value={postureRecs.length} hint="Ranked by impact" tone="accent" />
              </div>

              <Panel
                title="Score breakdown"
                hint="Where the score comes from — detect, protect, respond, recover, governance."
                action={
                  <Button size="sm" variant="secondary" onClick={recalcPosture} disabled={busy === "posture"}>
                    Recalculate
                  </Button>
                }
              >
                {posture?.breakdown ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {Object.entries(posture.breakdown as Record<string, number>).map(([k, v]) => (
                      <div key={k} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="capitalize text-content-secondary">{k}</span>
                          <span className="font-mono text-content-primary">{Number(v).toFixed(0)}</span>
                        </div>
                        <div className="h-1.5 bg-app-subtle rounded-full overflow-hidden">
                          <div
                            className="h-full bg-accent-primary"
                            style={{ width: `${Math.max(0, Math.min(100, Number(v)))}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState title="No posture score yet" description="Recalculate to generate the first measurement." />
                )}
              </Panel>

              <Panel title="Recommendations" hint="What raises the score fastest, with estimated cost and benefit.">
                {postureRecs.length === 0 ? (
                  <EmptyState title="Nothing outstanding" description="No recommendations are open right now." />
                ) : (
                  <div className="space-y-2">
                    {postureRecs.map((r: any) => (
                      <Row key={r.id}>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold text-content-primary">{r.title}</span>
                          <Badge className="bg-app-subtle text-content-secondary border-line-subtle">{r.priority} priority</Badge>
                          <Badge className="bg-app-subtle text-content-secondary border-line-subtle">{r.effort} effort</Badge>
                        </div>
                        <div>
                          Impact {r.impact_score} · cost ${Number(r.estimated_cost ?? 0).toLocaleString()} · benefit $
                          {Number(r.estimated_benefit ?? 0).toLocaleString()}
                        </div>
                      </Row>
                    ))}
                  </div>
                )}
              </Panel>
            </>
          )}

          {tab === "autonomy" && (
            <>
              <Panel
                title="Autonomy level"
                hint="How far NOCTRA may act before it needs a human decision. Actions are always recorded, never executed silently."
              >
                <div className="flex flex-wrap gap-2">
                  {["manual", "supervised", "autonomous", "fully_autonomous"].map((level) => {
                    const isCurrent = osConfig?.autonomy_level === level;
                    return (
                      <Button
                        key={level}
                        size="sm"
                        variant={isCurrent ? "primary" : "secondary"}
                        onClick={() => setAutonomy(level)}
                        disabled={busy === `autonomy-${level}`}
                      >
                        {level.replace(/_/g, " ")}
                        {isCurrent ? " · current" : ""}
                      </Button>
                    );
                  })}
                </div>
                {osConfig?.policies && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {Object.entries(osConfig.policies as Record<string, boolean>).map(([k, v]) => (
                      <Badge
                        key={k}
                        className={
                          v
                            ? "bg-status-success/15 text-status-success border-status-success/30"
                            : "bg-app-subtle text-content-tertiary border-line-subtle"
                        }
                      >
                        {k.replace(/_/g, " ")}: {v ? "on" : "off"}
                      </Badge>
                    ))}
                  </div>
                )}
              </Panel>

              {osMetrics && (
                <Panel title="Operating metrics" hint="What the automation has actually done for you.">
                  <div className="grid gap-2 sm:grid-cols-3">
                    {Object.entries(osMetrics as Record<string, any>)
                      .filter(([, v]) => typeof v === "number")
                      .map(([k, v]) => (
                        <div key={k} className="border border-line-subtle rounded-sm p-3 bg-app-subtle/40">
                          <p className="tech-label text-content-tertiary">{k.replace(/_/g, " ")}</p>
                          <p className="text-xl font-bold tabular-nums text-content-primary">{v}</p>
                        </div>
                      ))}
                  </div>
                </Panel>
              )}

              <Panel title="Decision log" hint="Every autonomy change and automated decision, in order.">
                {osLogs.length === 0 ? (
                  <EmptyState title="No decisions logged" description="Changes to autonomy and automated actions appear here." />
                ) : (
                  <div className="space-y-2">
                    {osLogs.map((l: any) => (
                      <Row key={l.id}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-content-primary">{l.title}</span>
                          <span className="font-mono text-content-tertiary">{l.created_at?.slice(0, 19).replace("T", " ")}</span>
                        </div>
                        {l.description && <div>{l.description}</div>}
                      </Row>
                    ))}
                  </div>
                )}
              </Panel>
            </>
          )}

          {tab === "paths" && (
            <Panel
              title="Routes to your crown jewels"
              hint="Each path is a chain an attacker could follow. Break one link and the whole path closes."
              action={
                <Button size="sm" onClick={analyzePaths} disabled={busy === "paths"}>
                  Analyse paths
                </Button>
              }
            >
              {paths.length === 0 ? (
                <EmptyState
                  title="No paths mapped yet"
                  description="Run an analysis to map how an attacker would reach your critical assets."
                />
              ) : (
                <div className="space-y-2">
                  {paths.map((p: any) => (
                    <Row key={p.id}>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-content-primary">{p.name || `Path ${p.id}`}</span>
                        <Badge
                          className={
                            p.risk_score >= 70
                              ? "bg-status-critical/15 text-status-critical border-status-critical/30"
                              : "bg-status-warning/15 text-status-warning border-status-warning/30"
                          }
                        >
                          risk {Number(p.risk_score ?? 0).toFixed(0)}
                        </Badge>
                      </div>
                      {Array.isArray(p.path) && (
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                          {p.path.map((n: any, i: number) => (
                            <span key={i} className="flex items-center gap-1.5">
                              <span className="px-2 py-0.5 rounded-sm bg-app-surface border border-line-subtle font-mono text-[11px]">
                                {n.name}
                                {n.technique_id ? ` · ${n.technique_id}` : ""}
                              </span>
                              {i < p.path.length - 1 && <span className="text-content-tertiary">→</span>}
                            </span>
                          ))}
                        </div>
                      )}
                    </Row>
                  ))}
                </div>
              )}
            </Panel>
          )}

          {tab === "external" && (
            <>
              <Panel
                title="What we watch"
                hint="Domains, brand terms and mailboxes monitored outside your perimeter."
                action={
                  <Button size="sm" onClick={scanExternal} disabled={busy === "drp"}>
                    Scan now
                  </Button>
                }
              >
                {monitors.length === 0 ? (
                  <EmptyState title="No monitors configured" description="Add a domain or brand term to start watching." />
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {monitors.map((m: any) => (
                      <Badge key={m.id} className="bg-app-subtle text-content-secondary border-line-subtle">
                        {m.name} · {m.keyword}
                      </Badge>
                    ))}
                  </div>
                )}
              </Panel>

              <Panel title="Findings" hint="Lookalike domains, leaked credentials and impersonation.">
                {drpFindings.length === 0 ? (
                  <EmptyState title="Nothing found" description="No brand abuse or leaked credentials detected." />
                ) : (
                  <div className="space-y-2">
                    {drpFindings.map((f: any) => (
                      <Row key={f.id}>
                        <div className="flex items-center gap-2 flex-wrap">
                          <SeverityBadge severity={f.severity} />
                          <span className="font-semibold text-content-primary">{f.title}</span>
                          <Badge className="bg-app-subtle text-content-tertiary border-line-subtle">{f.finding_type}</Badge>
                        </div>
                        <div>{f.description}</div>
                        <div className="text-content-tertiary">Source: {f.source}</div>
                      </Row>
                    ))}
                  </div>
                )}
              </Panel>
            </>
          )}

          {tab === "cloud" && (
            <>
              {cloudSummary && (
                <div className="grid gap-4 sm:grid-cols-4">
                  <StatCard label="Clusters" value={cloudSummary.total_clusters ?? clusters.length} />
                  <StatCard label="Workloads" value={cloudSummary.total_workloads ?? workloads.length} />
                  <StatCard
                    label="Privileged"
                    value={cloudSummary.privileged_workloads ?? cloudSummary.privileged ?? 0}
                    tone="warning"
                  />
                  <StatCard label="Open findings" value={cloudSummary.open_findings ?? cloudSummary.findings ?? 0} tone="critical" />
                </div>
              )}
              <div className="grid gap-4 lg:grid-cols-2">
                <Panel title="Clusters">
                  {clusters.length === 0 ? (
                    <EmptyState title="No clusters connected" />
                  ) : (
                    <div className="space-y-2">
                      {clusters.map((c: any) => (
                        <Row key={c.id}>
                          <span className="font-semibold text-content-primary">{c.name}</span>
                          <div>
                            {c.provider} · {c.region} · {c.node_count} node(s)
                          </div>
                        </Row>
                      ))}
                    </div>
                  )}
                </Panel>
                <Panel title="Workloads">
                  {workloads.length === 0 ? (
                    <EmptyState title="No workloads discovered" />
                  ) : (
                    <div className="space-y-2">
                      {workloads.map((w: any) => (
                        <Row key={w.id}>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-content-primary">{w.name}</span>
                            {w.is_privileged && (
                              <Badge className="bg-status-critical/15 text-status-critical border-status-critical/30">privileged</Badge>
                            )}
                          </div>
                          <div className="font-mono text-[11px]">
                            {w.namespace} · {w.image} · risk {w.risk_score}
                          </div>
                        </Row>
                      ))}
                    </div>
                  )}
                </Panel>
              </div>
            </>
          )}

          {tab === "redteam" && (
            <Panel
              title="Scheduled emulations"
              hint="Safe replays of real attacker techniques. Anything we fail to detect becomes a gap you can fix."
              action={
                <Button size="sm" onClick={createRedTeamJob} disabled={busy === "cart-create"}>
                  Schedule emulation
                </Button>
              }
            >
              {cartJobs.length === 0 ? (
                <EmptyState title="No emulations scheduled" description="Schedule one to test your detections nightly." />
              ) : (
                <div className="space-y-2">
                  {cartJobs.map((j: any) => (
                    <div
                      key={j.id}
                      className="border border-line-subtle rounded-sm p-3 bg-app-subtle/40 flex items-center justify-between gap-3"
                    >
                      <div className="text-xs text-content-secondary space-y-1">
                        <div className="font-semibold text-content-primary">{j.name}</div>
                        <div className="font-mono text-[11px]">
                          schedule {j.schedule_cron} · {j.status}
                        </div>
                      </div>
                      <Button size="sm" variant="secondary" onClick={() => runRedTeamJob(j.id)} disabled={busy === `cart-${j.id}`}>
                        Run now
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          )}

          {tab === "search" && (
            <Panel
              title="Query every source at once"
              hint={sources.length ? `Connected: ${sources.map((s: any) => s.name).join(", ")}` : "No sources connected yet."}
            >
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                spellCheck={false}
                aria-label="Unified query"
                className="w-full h-24 p-3 rounded-sm bg-app-subtle border border-line-subtle font-mono text-xs text-content-primary focus:outline-none focus:border-accent-primary"
              />
              <Button size="sm" onClick={runQuery} disabled={busy === "query"}>
                Run query
              </Button>
              {queryRes && <Json value={queryRes} />}
            </Panel>
          )}

          {tab === "routing" && (
            <>
              <Panel title="Route a case" hint="Assigns the case to the best-matched analyst or agent.">
                <div className="flex flex-wrap gap-2 items-center">
                  <input
                    value={caseId}
                    onChange={(e) => setCaseId(e.target.value)}
                    placeholder="Case number"
                    inputMode="numeric"
                    aria-label="Case number"
                    className="px-3 py-1.5 rounded-sm bg-app-subtle border border-line-subtle text-xs text-content-primary focus:outline-none focus:border-accent-primary"
                  />
                  <Button size="sm" onClick={orchestrate} disabled={busy === "orchestrate"}>
                    Route case
                  </Button>
                </div>
              </Panel>

              {dashboard?.agents && (
                <Panel title="Who is available" hint="Humans and agents, with what they are working on.">
                  <div className="grid gap-2 sm:grid-cols-2">
                    {asList(dashboard.agents).map((a: any, i: number) => (
                      <Row key={i}>
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-content-primary">{a.name}</span>
                          <Badge
                            className={
                              a.status === "idle"
                                ? "bg-status-success/15 text-status-success border-status-success/30"
                                : "bg-status-warning/15 text-status-warning border-status-warning/30"
                            }
                          >
                            {a.status}
                          </Badge>
                        </div>
                        {a.current_case_id && <div>Working case {a.current_case_id}</div>}
                      </Row>
                    ))}
                  </div>
                </Panel>
              )}

              <Panel title="Recent routing decisions">
                {orchestrations.length === 0 ? (
                  <EmptyState title="Nothing routed yet" />
                ) : (
                  <div className="space-y-2">
                    {orchestrations.map((o: any) => (
                      <Row key={o.id}>
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-content-primary">Case {o.case_id}</span>
                          <Badge className="bg-app-subtle text-content-secondary border-line-subtle">{o.status}</Badge>
                        </div>
                        {Array.isArray(o.workflow) && (
                          <div className="flex flex-wrap gap-1">
                            {o.workflow.map((s: any, i: number) => (
                              <span key={i} className="px-1.5 py-0.5 rounded-sm bg-app-surface border border-line-subtle text-[11px]">
                                {s.agent}
                              </span>
                            ))}
                          </div>
                        )}
                      </Row>
                    ))}
                  </div>
                )}
              </Panel>
            </>
          )}

          {tab === "sharing" && (
            <Panel
              title="Shared indicator packages"
              hint="Indicators are anonymised and traffic-light labelled before they leave your tenant."
              action={
                <Button size="sm" onClick={shareIntel} disabled={busy === "intel"}>
                  Share indicators
                </Button>
              }
            >
              {intel.length === 0 ? (
                <EmptyState title="Nothing shared yet" description="Share indicators with trusted peers when you confirm a threat." />
              ) : (
                <div className="space-y-2">
                  {intel.map((p: any) => (
                    <Row key={p.id}>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-content-primary">{p.name}</span>
                        <Badge className="bg-app-subtle text-content-secondary border-line-subtle">TLP:{p.tlp}</Badge>
                        {p.is_anonymized && (
                          <Badge className="bg-status-success/15 text-status-success border-status-success/30">anonymised</Badge>
                        )}
                      </div>
                      <div>Status: {p.status}</div>
                    </Row>
                  ))}
                </div>
              )}
            </Panel>
          )}

          {tab === "crypto" && (
            <Panel
              title="Where you rely on breakable encryption"
              hint="Inventory of algorithms in use, ranked by how urgently they need replacing."
              action={
                <Button size="sm" onClick={scanCrypto} disabled={busy === "crypto"}>
                  Scan inventory
                </Button>
              }
            >
              {crypto.length === 0 ? (
                <EmptyState title="No inventory yet" description="Scan to discover where encryption is used." />
              ) : (
                <div className="space-y-2">
                  {crypto.map((c: any) => (
                    <Row key={c.id}>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-content-primary">
                          {c.algorithm} {c.key_size}
                        </span>
                        <Badge
                          className={
                            c.is_quantum_safe
                              ? "bg-status-success/15 text-status-success border-status-success/30"
                              : "bg-status-warning/15 text-status-warning border-status-warning/30"
                          }
                        >
                          {c.is_quantum_safe ? "future-proof" : "needs replacing"}
                        </Badge>
                      </div>
                      <div>
                        Used for {c.usage} · risk {c.risk_score} · {c.migration_status}
                      </div>
                    </Row>
                  ))}
                </div>
              )}
            </Panel>
          )}
        </div>
      )}
    </div>
  );
}
