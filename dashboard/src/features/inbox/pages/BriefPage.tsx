import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Sparkles,
  Server,
  User as UserIcon,
  Globe,
  AppWindow,
  ShieldCheck,
  RefreshCw,
  Moon,
  Inbox as InboxIcon,
} from "lucide-react";
import { Button, PageHeader, SeverityBadge, SkeletonCard, SkeletonChart, StatusBadge, Term } from "../../../components/ui";
import { Select } from "../../../components/ui/Select";
import OnboardingChecklist, { type OnboardingStep } from "../../../components/OnboardingChecklist";
import AnalystApi from "../../../api/analystApi";
import type { Brief, Connector, AnalystCase } from "../../../types/analyst";
import { getApiError } from "../../../utils/getApiError";

/**
 * Home — the Analyst Inbox (spec §7, §21).
 * Every number on this screen comes from the real /analyst/brief response.
 * Nothing is fabricated: no fake posture score, no placeholder alerts. When
 * nothing is pending we say so plainly and show how to see the loop end-to-end.
 */

const timeOf = (iso?: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? "—"
    : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const NODE_ICON: Record<string, typeof Server> = {
  host: Server,
  account: UserIcon,
  ip: Globe,
  domain: Globe,
  email: UserIcon,
  file: AppWindow,
  hash: AppWindow,
};

const connectorTone = (status: Connector["status"]): "success" | "warning" | "critical" => {
  switch (status) {
    case "connected":
      return "success";
    case "syncing":
      return "warning";
    default:
      return "critical";
  }
};

const BriefPage: React.FC = () => {
  const navigate = useNavigate();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [feedCases, setFeedCases] = useState<AnalystCase[]>([]);
  const [onboardingDismissed, setOnboardingDismissed] = useState<boolean>(
    () => localStorage.getItem("noctra_onboarding_dismissed") === "1"
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [selectedScenario, setSelectedScenario] = useState("credential_leak");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [briefData, connData, feedData] = await Promise.all([
        AnalystApi.fetchBrief(),
        AnalystApi.fetchConnectors().catch(() => []),
        AnalystApi.fetchFeed({ page: 1, limit: 100 }).catch(() => ({ data: [] as AnalystCase[] })),
      ]);
      setBrief(briefData);
      setConnectors(connData);
      setFeedCases(Array.isArray(feedData) ? feedData : feedData?.data ?? []);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load your brief"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSimulate = async () => {
    setSimulating(true);
    setError(null);
    try {
      const created = await AnalystApi.simulate(selectedScenario);
      navigate(`/case/${created.id}`);
    } catch (err: any) {
      setError(getApiError(err, "Could not simulate a scenario"));
      setSimulating(false);
    }
  };

  const handleSyncConnector = async (id: string) => {
    setSyncingId(id);
    try {
      await AnalystApi.syncConnector(id);
      setConnectors((prev) =>
        prev.map((c) => (c.id === id ? { ...c, last_sync: "Just now" } : c))
      );
    } catch (err: any) {
      setError(getApiError(err, "Connector sync failed"));
    } finally {
      setSyncingId(null);
    }
  };

  const pendingCases: AnalystCase[] = brief?.top_cases ?? [];
  const latestCase = pendingCases[0];
  const analysis = latestCase?.analysis ?? null;

  // First-run checklist — every step derived from real data or real visits.
  const onboardingSteps: OnboardingStep[] = [
    {
      id: "telemetry",
      label: "Telemetry is flowing",
      hint: "Run a simulation (top right) or send logs — assets become observable.",
      done: (brief?.watching ?? 0) > 0,
    },
    {
      id: "case",
      label: "Open your first case",
      hint: "A case is one incident: the story, the blast radius, one decision.",
      to: "/feed",
      done: feedCases.length > 0,
    },
    {
      id: "decision",
      label: "Make your first decision",
      hint: "Approve or decline — approving records a reversible action.",
      to: latestCase ? `/case/${latestCase.id}` : "/feed",
      done: feedCases.some((c) => c.decision !== "pending"),
    },
    {
      id: "record",
      label: "See the decision recorded",
      hint: "The Actions log is the audit trail of what was recorded.",
      to: "/actions",
      done: localStorage.getItem("noctra_visited_actions") === "1" || feedCases.some((c) => c.decision === "approved"),
    },
    {
      id: "report",
      label: "Read a case report",
      hint: "Every decision generates a markdown report you can download.",
      to: "/reports",
      done: localStorage.getItem("noctra_visited_reports") === "1" || feedCases.some((c) => c.report),
    },
  ];

  const dismissOnboarding = () => {
    localStorage.setItem("noctra_onboarding_dismissed", "1");
    setOnboardingDismissed(true);
  };
  const blastChips =
    latestCase?.blast_radius?.nodes?.slice(0, 4).map((n) => ({
      icon: NODE_ICON[n.entity_type] ?? AppWindow,
      label: `${n.entity_type}: ${n.value}`,
    })) ?? [];

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <PageHeader
          title="Analyst Inbox"
          description="What NOCTRA found while you were away."
        />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <SkeletonChart className="h-64" />
            <SkeletonChart className="h-56" />
          </div>
          <div className="space-y-6">
            <SkeletonCard className="h-40" />
            <SkeletonCard className="h-40" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Analyst Inbox"
        description={
          brief
            ? (
                <>
                  {brief.alerts_today} event{brief.alerts_today === 1 ? "" : "s"} investigated today ·{" "}
                  {brief.auto_recorded_today} <Term>auto-recorded</Term> response
                  {brief.auto_recorded_today === 1 ? "" : "s"} · {brief.handled_today} decision
                  {brief.handled_today === 1 ? "" : "s"} by you · {brief.pending_count} waiting.
                </>
              )
            : "What NOCTRA found while you were away."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
            <Select
              inline
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
              disabled={simulating}
              aria-label="Scenario to simulate"
              className="flex-1 sm:flex-none sm:min-w-[190px] bg-app-subtle text-xs"
              options={[
                { value: "credential_leak", label: "Credential Leak (T1078)" },
                { value: "phishing_outbreak", label: "Phishing Outbreak (T1566)" },
                { value: "data_exfiltration", label: "Data Exfiltration (T1048)" },
                { value: "compromised_api_key", label: "Compromised API Key (T1098)" },
              ]}
            />
            <Button variant="primary" onClick={handleSimulate} disabled={simulating} className="text-xs px-4 py-2">
              <Sparkles size={14} className="mr-1.5" aria-hidden />
              {simulating ? "Simulating…" : "Simulate scenario"}
            </Button>
          </div>
        }
      />

      {error && (
        <div
          role="alert"
          className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical font-medium"
        >
          {error}
        </div>
      )}

      {!onboardingDismissed && <OnboardingChecklist steps={onboardingSteps} onDismiss={dismissOnboarding} />}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Lead card — the one thing that needs a decision, on the night canvas. */}
        <div className="night console-panel hud-corners lg:col-span-7 text-content-primary rounded-sm p-6 flex flex-col justify-between min-h-[320px]">
          {latestCase ? (
            <>
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-bold tracking-wider text-content-tertiary uppercase">
                    <Term>Needs your decision</Term>
                  </span>
                  <SeverityBadge severity={latestCase.priority} />
                </div>

                <h2 className="text-lg font-bold font-display text-content-primary mt-3 mb-2 leading-snug">
                  {analysis?.headline || latestCase.title}
                </h2>

                <p className="text-xs text-content-secondary leading-relaxed mb-2">
                  {analysis?.what_happened || latestCase.description || "Summary unavailable for this case."}
                </p>

                {analysis?.why_it_matters && (
                  <div className="mb-2">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary mb-0.5">
                      Why it matters
                    </p>
                    <p className="text-xs text-content-secondary leading-relaxed">{analysis.why_it_matters}</p>
                  </div>
                )}

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-2">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Affected</p>
                    <p className="text-sm font-bold text-content-primary font-mono mt-0.5">
                      {latestCase.blast_radius?.nodes?.length ?? 0} systems
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Confidence</p>
                    <p className="text-sm font-bold text-content-primary font-mono mt-0.5">
                      {analysis && !analysis.fallback ? `${Math.round((analysis.confidence ?? 0) * 100)}%` : "n/a"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Recommends</p>
                    <p
                      className="text-sm font-bold text-accent-secondary font-mono mt-0.5 truncate"
                      title={latestCase.proposed_action?.action_type}
                    >
                      {latestCase.proposed_action?.action_type ?? "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Reversible</p>
                    <p className="text-sm font-bold text-content-primary font-mono mt-0.5">
                      {latestCase.proposed_action?.undo ? "Yes" : "Ask"}
                    </p>
                  </div>
                </div>

                <p className="text-[11px] text-content-tertiary font-mono">
                  {analysis
                    ? analysis.fallback
                      ? "Rule-based analysis (model unavailable) · confidence n/a"
                      : `${analysis.model} · confidence ${Math.round((analysis.confidence ?? 0) * 100)}%`
                    : "No analysis recorded yet"}
                </p>

                <div className="space-y-2 mt-4">
                  <p className="text-[11px] font-semibold text-content-secondary">
                    Observed blast radius
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {blastChips.length > 0 ? (
                      blastChips.map((chip) => (
                        <span
                          key={chip.label}
                          className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono bg-app-subtle/80 text-content-secondary border border-line-bright"
                        >
                          <chip.icon size={12} className="text-content-tertiary" /> {chip.label}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-content-tertiary font-mono">
                        No affected assets mapped for this case.
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-6 flex justify-end">
                <button
                  type="button"
                  onClick={() => navigate(`/case/${latestCase.id}`)}
                  className="bg-brand-gradient hover:-translate-y-0.5 hover:shadow-signal hover:opacity-95 text-brand-ink font-semibold text-xs px-5 py-2.5 rounded-sm transition"
                >
                  Review case #{latestCase.id}
                </button>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-start justify-center h-full gap-3 py-6">
              <Moon size={22} className="text-accent-secondary" aria-hidden />
              <h2 className="text-lg font-bold font-display text-content-primary">
                Nothing needs you right now.
              </h2>
              <p className="text-xs text-content-secondary leading-relaxed max-w-md">
                {brief
                  ? `NOCTRA is watching ${brief.watching} asset${brief.watching === 1 ? "" : "s"} and has handled ${brief.handled_today} event${brief.handled_today === 1 ? "" : "s"} today. When something deserves attention, it lands here with a recommended, reversible action.`
                  : "When something deserves attention, it lands here with a recommended, reversible action."}
              </p>
              <p className="text-[11px] text-content-tertiary">
                New here? Simulate a scenario (top right) to watch the full loop end-to-end.
              </p>
            </div>
          )}
        </div>

        {/* Queue — every pending decision, straight from the brief. */}
        <div className="lg:col-span-5 flex flex-col gap-4 min-h-[320px]">
          <div className="bg-app-surface rounded-2xl border border-line-subtle p-5 shadow-card flex-1 flex flex-col">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold tracking-wider text-content-tertiary uppercase">
                Awaiting decision
              </span>
              <InboxIcon size={14} className="text-content-tertiary" aria-hidden />
            </div>
            {pendingCases.length > 0 ? (
              <ul className="mt-3 divide-y divide-line-subtle">
                {pendingCases.slice(0, 6).map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => navigate(`/case/${c.id}`)}
                      className="w-full flex items-center justify-between gap-3 text-left py-2.5 group"
                    >
                      <span className="text-xs font-medium text-content-secondary group-hover:text-content-primary transition truncate">
                        {c.analysis?.headline || c.title}
                      </span>
                      <span className="flex items-center gap-2 shrink-0">
                        <SeverityBadge severity={c.priority} />
                        <span className="text-content-tertiary font-mono text-[11px]">
                          {timeOf(c.created_at)}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-xs text-content-tertiary">
                The queue is empty — no cases are waiting on a decision.
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-app-surface rounded-2xl border border-line-subtle p-5 shadow-card">
              <p className="text-[11px] font-bold tracking-wider text-content-tertiary uppercase">
                Handled today
              </p>
              <p className="mt-2 text-3xl font-extrabold font-display text-content-primary">
                {brief?.handled_today ?? 0}
              </p>
              <p className="text-[11px] text-content-tertiary mt-1">decisions closed</p>
            </div>
            <div className="bg-app-surface rounded-2xl border border-line-subtle p-5 shadow-card">
              <p className="text-[11px] font-bold tracking-wider text-content-tertiary uppercase">
                Watching
              </p>
              <p className="mt-2 text-3xl font-extrabold font-display text-content-primary">
                {brief?.watching ?? 0}
              </p>
              <p className="text-[11px] text-content-tertiary mt-1">assets under observation</p>
            </div>
          </div>
        </div>
      </div>

      {/* Integrated tooling — statuses exactly as reported by the backend. */}
      <div className="bg-app-surface rounded-2xl border border-line-subtle p-6 shadow-card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-bold text-content-primary flex items-center gap-2 font-display">
              <ShieldCheck size={16} className="text-accent-primary" /> Integrated security tooling
            </h2>
            <p className="text-xs text-content-tertiary mt-0.5">
              Telemetry sources feeding NOCTRA's analysis.
            </p>
          </div>
        </div>

        {connectors.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {connectors.map((conn) => (
              <div
                key={conn.id}
                className="p-4 rounded-xl bg-app-subtle border border-line-subtle flex flex-col justify-between space-y-3"
              >
                <div>
                  <div className="flex items-center justify-between mb-1 gap-2">
                    <span className="text-xs font-bold text-content-primary truncate">
                      {conn.name}
                    </span>
                    <StatusBadge tone={connectorTone(conn.status)} label={conn.status} />
                  </div>
                  <p className="text-[11px] text-content-tertiary">{conn.category}</p>
                </div>

                <div className="flex items-center justify-between text-[11px] text-content-secondary border-t border-line-subtle pt-2">
                  <span>{conn.assets_monitored} assets</span>
                  <button
                    type="button"
                    onClick={() => handleSyncConnector(conn.id)}
                    disabled={syncingId === conn.id}
                    className="flex items-center gap-1 text-accent-primary font-semibold hover:underline text-[11px]"
                  >
                    <RefreshCw size={10} className={syncingId === conn.id ? "animate-spin" : ""} />
                    {conn.last_sync}
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-content-tertiary">
            No connector telemetry configured for this environment.
          </p>
        )}
      </div>
    </div>
  );
};

export default BriefPage;
