import React, { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import AnalyticsApi from "../../../api/analyticsApi";
import MlApi from "../../../api/mlApi";
import type { BenchmarkReport, ExplainKind, ExplanationResponse } from "../../../types/ml";
import type { OverviewStats, TopThreat, TrendPoint } from "../../../types/analytics";
import { PageHeader, SkeletonChart, SkeletonList, SkeletonStatCard, StatCard } from "../../../components/ui";
import { getApiError } from "../../../utils/getApiError";
import { CHART_TOOLTIP_STYLE, SEVERITY_COLORS } from "../../../components/ui/chartTokens";
import { Select } from "../../../components/ui/Select";

const EMPTY_OVERVIEW: OverviewStats = {
  total: 0,
  critical: 0,
  high: 0,
  medium: 0,
  low: 0,
  severity_distribution: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 },
  by_type: {},
  recent: [],
};


const AIAnalyticsPage: React.FC = () => {
  const [overview, setOverview] = useState<OverviewStats>(EMPTY_OVERVIEW);
  const [threats, setThreats] = useState<TopThreat[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [benchmark, setBenchmark] = useState<BenchmarkReport | null>(null);
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null);

  const [explainKind, setExplainKind] = useState<ExplainKind>("log");
  const [explainInput, setExplainInput] = useState(
    "SQL injection exploit detected on database"
  );
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      AnalyticsApi.getOverview(),
      AnalyticsApi.getTopThreats(10),
      AnalyticsApi.getAlertTrends(7),
    ])
      .then(([ov, th, tr]) => {
        if (cancelled) return;
        setOverview(ov || EMPTY_OVERVIEW);
        setThreats(th || []);
        setTrend(tr?.trend || []);
      })
      .catch((err: any) => {
        if (!cancelled) setError(getApiError(err, "Failed to load analytics data"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    MlApi.fetchBenchmark()
      .then((report) => {
        if (!cancelled) setBenchmark(report);
      })
      .catch(() => {
        if (!cancelled) setBenchmarkError("Unable to reach the ML benchmark (service down?).");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleExplain = async () => {
    if (!explainInput.trim()) return;
    setExplainLoading(true);
    setExplainError(null);
    try {
      const result = await MlApi.explain(explainKind, explainInput.trim());
      setExplanation(result);
    } catch (err: any) {
      setExplainError(getApiError(err, "Failed to compute explanation"));
    } finally {
      setExplainLoading(false);
    }
  };

  const kpis = [
    { label: "Total Alerts", value: overview.total, tone: "default" as const },
    { label: "Critical", value: overview.critical, tone: "critical" as const },
    { label: "High", value: overview.high, tone: "warning" as const },
    { label: "Medium", value: overview.medium, tone: "warning" as const },
    { label: "Low", value: overview.low, tone: "success" as const },
  ];

  const pieData = [
    { name: "CRITICAL", value: overview.severity_distribution?.CRITICAL || 0 },
    { name: "HIGH", value: overview.severity_distribution?.HIGH || 0 },
    { name: "MEDIUM", value: overview.severity_distribution?.MEDIUM || 0 },
    { name: "LOW", value: overview.severity_distribution?.LOW || 0 },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="AI Analytics"
        description="Aggregated detection telemetry from the AI threat engine."
      />

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      {loading ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonStatCard key={i} />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <SkeletonChart className="h-80" />
            <SkeletonChart className="h-80" />
          </div>
          <SkeletonList rows={4} />
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {kpis.map((kpi) => (
              <StatCard key={kpi.label} label={kpi.label} value={kpi.value} tone={kpi.tone} />
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-card">
              <h3 className="text-sm font-semibold text-content-primary">Alert Trend (7 days)</h3>
              <div className="h-64 mt-4" role="img" aria-label="Line chart: alert trend over the last 7 days, total and by severity">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend} margin={{ top: 5, right: 10, bottom: 5, left: -20 }}>
                    <CartesianGrid stroke="rgb(var(--c-line-subtle))" strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fill: "rgb(var(--c-content-tertiary))", fontSize: 11 }} />
                    <YAxis tick={{ fill: "rgb(var(--c-content-tertiary))", fontSize: 11 }} allowDecimals={false} />
                    <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                    <Line type="monotone" dataKey="total" stroke="#e5a54b" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="critical" stroke="#f26d6d" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="high" stroke="#f0824f" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-card">
              <h3 className="text-sm font-semibold text-content-primary">Severity Distribution</h3>
              <div className="h-56 mt-4" role="img" aria-label="Pie chart: share of alerts by severity">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={78}
                      innerRadius={44}
                      paddingAngle={2}
                      labelLine={false}
                    >
                      {pieData.map((entry) => (
                        <Cell key={entry.name} fill={SEVERITY_COLORS[entry.name] || "rgb(var(--c-content-tertiary))"} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5 mt-3">
                {pieData.map((entry) => (
                  <span key={entry.name} className="inline-flex items-center gap-1.5 text-xs text-content-secondary">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: SEVERITY_COLORS[entry.name] || "rgb(var(--c-content-tertiary))" }}
                    />
                    {entry.name.charAt(0) + entry.name.slice(1).toLowerCase()}
                    <span className="font-mono text-content-tertiary">{entry.value}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-card">
              <h3 className="text-sm font-semibold text-content-primary mb-4">Top Threats</h3>
              {threats.length === 0 ? (
                <p className="text-sm text-content-tertiary">No threat patterns detected yet.</p>
              ) : (
                <div className="space-y-3">
                  {threats.map((t, idx) => (
                    <div key={idx} className="flex items-center gap-3">
                      <span className="w-5 text-xs font-mono text-content-tertiary">{idx + 1}</span>
                      <div className="flex-1">
                        <p className="text-sm text-content-primary truncate">{t.threat}</p>
                        <div className="h-1.5 bg-app-subtle rounded-full mt-1 overflow-hidden">
                          <div
                            className="h-full bg-accent-primary rounded-full"
                            style={{ width: `${Math.min(100, (t.count / threats[0].count) * 100)}%` }}
                          />
                        </div>
                      </div>
                      <span className="text-xs font-mono text-content-secondary">{t.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-card">
              <h3 className="text-sm font-semibold text-content-primary mb-4">Detections by Type</h3>
              {Object.keys(overview.by_type || {}).length === 0 ? (
                <p className="text-sm text-content-tertiary">No detections recorded yet.</p>
              ) : (
                <div className="h-56" role="img" aria-label="Bar chart: detection counts by alert type">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={Object.entries(overview.by_type || {}).map(([name, value]) => ({ name, value }))}>
                      <CartesianGrid stroke="rgb(var(--c-line-subtle))" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="name" tick={{ fill: "rgb(var(--c-content-tertiary))", fontSize: 11 }} />
                      <YAxis tick={{ fill: "rgb(var(--c-content-tertiary))", fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                      <Bar dataKey="value" fill="rgb(var(--c-accent-primary))" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          <div className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-card">
            <h3 className="text-sm font-semibold text-content-primary mb-4">Recent Detections</h3>
            {overview.recent.length === 0 ? (
              <p className="text-sm text-content-tertiary">No recent alerts.</p>
            ) : (
              <div className="space-y-2">
                {overview.recent.map((alert) => (
                  <div
                    key={alert.id}
                    className="flex items-center justify-between gap-4 px-4 py-2.5 rounded-lg bg-app-bg border border-line-subtle"
                  >
                    <span className="text-sm text-content-primary truncate">{alert.message}</span>
                    <div className="flex items-center gap-3 shrink-0">
                      <span
                        className="px-2 py-0.5 rounded text-xs font-semibold"
                        style={{
                          color: SEVERITY_COLORS[alert.severity] || "#a1a1aa",
                          backgroundColor: `${SEVERITY_COLORS[alert.severity] || "#a1a1aa"}22`,
                        }}
                      >
                        {alert.severity}
                      </span>
                      <span className="text-xs text-content-tertiary whitespace-nowrap">
                        {alert.created_at ? new Date(alert.created_at).toLocaleString() : "-"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-card">
              <h3 className="text-sm font-semibold text-content-primary mb-4">Model Explainability</h3>
              <p className="text-xs text-content-tertiary mb-4">
                Why did the model flag this? Paste a sample to see the contributing signals.
              </p>
              <div className="flex flex-col sm:flex-row gap-3 mb-3">
                <Select
                  inline
                  value={explainKind}
                  onChange={(e) => setExplainKind(e.target.value as ExplainKind)}
                  className="flex-1 sm:flex-none sm:w-52"
                  options={[
                    { value: "log", label: "Security log" },
                    { value: "email", label: "Email" },
                    { value: "network", label: "Network flow (port,bytes)" },
                    { value: "dns", label: "DNS domain" },
                  ]}
                />
                <input
                  type="text"
                  value={explainInput}
                  onChange={(e) => setExplainInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleExplain()}
                  placeholder={
                    explainKind === "network"
                      ? "e.g. 3389, 25000000"
                      : explainKind === "dns"
                      ? "e.g. update-account.tk"
                      : "Paste log / email text…"
                  }
                  className="flex-1 px-3.5 py-2 bg-app-bg border border-line-subtle rounded-lg text-sm text-content-primary focus:outline-none focus:border-accent-primary"
                />
                <button
                  type="button"
                  onClick={handleExplain}
                  disabled={explainLoading}
                  className="px-4 py-2 rounded-full bg-accent-primary/10 hover:bg-accent-primary/20 border border-accent-primary/30 text-sm font-medium text-accent-primary transition disabled:opacity-40"
                >
                  {explainLoading ? "Explaining…" : "Explain"}
                </button>
              </div>

              {explainError && (
                <p className="text-xs text-status-critical mb-3">{explainError}</p>
              )}

              {explanation && (
                <div className="space-y-2">
                  <p className="text-sm text-content-secondary">{explanation.summary}</p>
                  <div className="space-y-1.5">
                    {explanation.contributions.length === 0 ? (
                      <p className="text-xs text-content-tertiary">No strong signals found.</p>
                    ) : (
                      explanation.contributions.map((c, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-app-bg border border-line-subtle"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span
                              className={`w-2 h-2 rounded-full shrink-0 ${
                                c.direction === "attack"
                                  ? "bg-status-critical"
                                  : c.direction === "attention"
                                  ? "bg-status-warning"
                                  : "bg-status-success"
                              }`}
                            />
                            <span className="text-sm text-content-primary truncate">{c.term}</span>
                          </div>
                          <span className="text-xs font-mono text-content-secondary shrink-0">
                            {typeof c.score === "number" ? c.score.toFixed(3) : "-"}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                  <p className="text-[11px] text-content-tertiary pt-1">{explanation.method}</p>
                </div>
              )}
            </div>

            <div className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-card">
              <h3 className="text-sm font-semibold text-content-primary mb-4">Model Benchmark</h3>
              {benchmarkError ? (
                <p className="text-xs text-content-tertiary">{benchmarkError}</p>
              ) : !benchmark ? (
                <p className="text-xs text-content-tertiary">Loading benchmark…</p>
              ) : (
                <div className="space-y-3">
                  {benchmark.models.map((m) => (
                    <div
                      key={m.model}
                      className="px-4 py-3 rounded-lg bg-app-bg border border-line-subtle"
                    >
                      <div className="flex items-center justify-between gap-3 mb-1.5">
                        <span className="text-sm font-medium text-content-primary font-mono">
                          {m.model}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            m.status === "ok"
                              ? "bg-status-success/15 text-status-success"
                              : "bg-status-warning/15 text-status-warning"
                          }`}
                        >
                          {m.status}
                        </span>
                      </div>
                      <p className="text-xs text-content-tertiary mb-2">{m.model_type}</p>
                      {m.metrics ? (
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(m.metrics).map(([k, v]) =>
                            typeof v === "number" ? (
                              <span
                                key={k}
                                className="px-2 py-0.5 rounded bg-app-subtle border border-line-subtle text-[11px] font-mono text-content-secondary"
                              >
                                {k.replace(/_/g, " ")}: {v.toFixed(3)}
                              </span>
                            ) : null
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-content-tertiary">{m.reason || "No metrics"}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default AIAnalyticsPage;
