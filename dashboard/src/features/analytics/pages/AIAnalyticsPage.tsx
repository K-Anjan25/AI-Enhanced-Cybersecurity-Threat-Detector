import React, { useEffect, useMemo, useState } from "react";
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
  Sector,
} from "recharts";
import AnalyticsApi from "../../../api/analyticsApi";
import MlApi from "../../../api/mlApi";
import type { BenchmarkReport, ExplainKind, ExplanationResponse } from "../../../types/ml";
import type { OverviewStats, TopThreat, TrendPoint } from "../../../types/analytics";
import { PageHeader, SkeletonChart, SkeletonList, SkeletonStatCard, Spinner, StatCard } from "../../../components/ui";
import { getApiError } from "../../../utils/getApiError";
import { SEVERITY_COLORS } from "../../../components/ui/chartTokens";
import { useIsMobile } from "../../../hooks";
import { Select } from "../../../components/ui/Select";

const formatDate = (iso?: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
};

const formatDay = (iso: string): string => {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

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

/* -------------------------------------------------------------------------- */
/* Chart building blocks — series definitions, tooltips, hover states         */
/* -------------------------------------------------------------------------- */

type TrendKey = "total" | "critical" | "high" | "medium" | "low";

const TREND_SERIES: { key: TrendKey; label: string; color: string }[] = [
  { key: "total", label: "Total", color: "#e5a54b" },
  { key: "critical", label: "Critical", color: SEVERITY_COLORS.CRITICAL },
  { key: "high", label: "High", color: SEVERITY_COLORS.HIGH },
  { key: "medium", label: "Medium", color: SEVERITY_COLORS.MEDIUM },
  { key: "low", label: "Low", color: SEVERITY_COLORS.LOW },
];

const TrendTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-xl border border-line-bright bg-app-surface px-3 py-2.5 shadow-overlay">
      <p className="mb-1.5 text-xs font-semibold text-content-primary">{label}</p>
      <div className="space-y-1">
        {payload.map((p: any) => (
          <div key={p.dataKey} className="flex items-center gap-2 text-xs">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: p.stroke || p.color || "rgb(var(--c-content-tertiary))" }}
            />
            <span className="text-content-secondary">{p.name}</span>
            <span className="ml-auto pl-5 font-mono text-content-primary tabular-nums">{p.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

const SeverityTooltip = ({ active, payload, total }: any) => {
  if (!active || !payload || payload.length === 0) return null;
  const entry = payload[0];
  const value = Number(entry?.value) || 0;
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="rounded-xl border border-line-bright bg-app-surface px-3 py-2 shadow-overlay text-xs">
      <p className="mb-0.5 font-semibold text-content-primary">
        {entry.name?.charAt(0) + entry.name?.slice(1).toLowerCase()}
      </p>
      <p className="text-content-secondary">
        {value} alert{value === 1 ? "" : "s"} · <span className="font-mono">{pct}%</span> of total
      </p>
    </div>
  );
};

const TypeTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload || payload.length === 0) return null;
  const value = Number(payload[0]?.value) || 0;
  return (
    <div className="rounded-xl border border-line-bright bg-app-surface px-3 py-2 shadow-overlay text-xs">
      <p className="mb-0.5 font-semibold text-content-primary">{label}</p>
      <p className="text-content-secondary">
        {value} detection{value === 1 ? "" : "s"}
      </p>
    </div>
  );
};

/** Hover state for the severity donut: gently push the active slice outward. */
const renderActivePie = (props: any) => {
  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props;
  return (
    <g>
      <Sector
        cx={cx}
        cy={cy}
        innerRadius={innerRadius}
        outerRadius={Math.min((Number(outerRadius) || 0) + 6, 120)}
        startAngle={startAngle}
        endAngle={endAngle}
        fill={fill}
      />
    </g>
  );
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

  const [trendDays, setTrendDays] = useState(7);
  const [trendLoading, setTrendLoading] = useState(false);
  const [hiddenSeries, setHiddenSeries] = useState<string[]>([]);
  const [pieActive, setPieActive] = useState<number | null>(null);
  const isMobile = useIsMobile();

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

  // Trend chart: range switching + clickable series legend.
  const loadTrend = async (days: number) => {
    setTrendLoading(true);
    try {
      const tr = await AnalyticsApi.getAlertTrends(days);
      setTrend(tr?.trend || []);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load alert trend"));
    } finally {
      setTrendLoading(false);
    }
  };

  const changeRange = (days: number) => {
    if (days === trendDays) return;
    setTrendDays(days);
    setHiddenSeries([]);
    loadTrend(days);
  };

  const toggleSeries = (key: string) =>
    setHiddenSeries((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  const trendSummary = useMemo(() => {
    if (!trend.length) return null;
    const total = trend.reduce((s, t) => s + (Number(t.total) || 0), 0);
    const peak = trend.reduce((m, t) =>
      (Number(t.total) || 0) > (Number(m.total) || 0) ? t : m, trend[0]
    );
    return { total, avg: total / trend.length, peak };
  }, [trend]);

  const typeData = useMemo(
    () => Object.entries(overview.by_type || {}).map(([name, value]) => ({ name, value })),
    [overview.by_type]
  );

  const kpis = [
    { label: "Total Alerts", value: overview.total, tone: "default" as const },
    { label: "Critical", value: overview.critical, tone: "critical" as const },
    { label: "High", value: overview.high, tone: "warning" as const },
    { label: "Medium", value: overview.medium, tone: "warning" as const },
    { label: "Low", value: overview.low, tone: "success" as const },
  ];

  const maxThreatCount =
    threats.reduce((m, t) => Math.max(m, t.count || 0), 0) || 1;

  const pieData = [
    { name: "CRITICAL", value: overview.severity_distribution?.CRITICAL || 0 },
    { name: "HIGH", value: overview.severity_distribution?.HIGH || 0 },
    { name: "MEDIUM", value: overview.severity_distribution?.MEDIUM || 0 },
    { name: "LOW", value: overview.severity_distribution?.LOW || 0 },
  ];

  const pieTotal = pieData.reduce((s, d) => s + (Number(d.value) || 0), 0);

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
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-content-primary">Alert Trend</h3>
                  <p className="text-xs text-content-tertiary mt-0.5">
                    Daily alerts over the last {trendDays} days, split by severity.
                  </p>
                </div>
                <div
                  className="flex items-center gap-1 p-1 rounded-full bg-app-subtle border border-line-subtle"
                  role="group"
                  aria-label="Trend range"
                >
                  {[7, 14, 30, 90].map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => changeRange(d)}
                      className={`px-2.5 py-1 rounded-full text-xs font-semibold transition ${
                        trendDays === d
                          ? "bg-brand-gradient text-brand-ink shadow-float"
                          : "text-content-secondary hover:text-content-primary"
                      }`}
                    >
                      {d}D
                    </button>
                  ))}
                </div>
              </div>

              {trendSummary && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
                  <div className="rounded-xl bg-app-bg border border-line-subtle px-3 py-2">
                    <p className="text-[10px] uppercase tracking-wider text-content-tertiary">Total alerts</p>
                    <p className="text-lg font-bold text-content-primary tabular-nums">{trendSummary.total}</p>
                  </div>
                  <div className="rounded-xl bg-app-bg border border-line-subtle px-3 py-2">
                    <p className="text-[10px] uppercase tracking-wider text-content-tertiary">Avg / day</p>
                    <p className="text-lg font-bold text-content-primary tabular-nums">{trendSummary.avg.toFixed(1)}</p>
                  </div>
                  <div className="rounded-xl bg-app-bg border border-line-subtle px-3 py-2 min-w-0">
                    <p className="text-[10px] uppercase tracking-wider text-content-tertiary">Peak day</p>
                    <p className="text-sm font-semibold text-content-primary truncate">
                      {formatDay(trendSummary.peak.date)} · {trendSummary.peak.total}
                    </p>
                  </div>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mt-4">
                {TREND_SERIES.map((s) => {
                  const hidden = hiddenSeries.includes(s.key);
                  const sum = trend.reduce((acc, t) => acc + (Number(t[s.key]) || 0), 0);
                  return (
                    <button
                      key={s.key}
                      type="button"
                      onClick={() => toggleSeries(s.key)}
                      aria-pressed={!hidden}
                      title={hidden ? `Show ${s.label}` : `Hide ${s.label}`}
                      className={`inline-flex items-center gap-1.5 text-xs rounded-md px-1.5 py-0.5 transition ${
                        hidden ? "opacity-40 hover:opacity-70" : "hover:bg-app-subtle"
                      }`}
                    >
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
                      <span className="text-content-secondary">{s.label}</span>
                      <span className="font-mono text-content-tertiary tabular-nums">{sum}</span>
                    </button>
                  );
                })}
              </div>

              <div className="relative">
                <div
                  className={`h-64 mt-3 transition-opacity duration-200 ${trendLoading ? "opacity-40 pointer-events-none" : ""}`}
                  role="img"
                  aria-label={`Line chart: alert trend over the last ${trendDays} days, total and by severity`}
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trend} margin={{ top: 5, right: 10, bottom: 5, left: -20 }}>
                      <CartesianGrid stroke="rgb(var(--c-line-subtle))" strokeDasharray="3 3" />
                      <XAxis
                        dataKey="date"
                        tickFormatter={formatDay}
                        tick={{ fill: "rgb(var(--c-content-tertiary))", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        minTickGap={24}
                      />
                      <YAxis
                        tick={{ fill: "rgb(var(--c-content-tertiary))", fontSize: 11 }}
                        allowDecimals={false}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip content={<TrendTooltip />} cursor={{ stroke: "rgb(var(--c-line-bright))", strokeDasharray: "3 3" }} />
                      {TREND_SERIES.filter((s) => !hiddenSeries.includes(s.key)).map((s) => (
                        <Line
                          key={s.key}
                          type="monotone"
                          dataKey={s.key}
                          name={s.label}
                          stroke={s.color}
                          strokeWidth={2}
                          dot={trendDays <= 14 ? { r: 2.5, strokeWidth: 0 } : false}
                          activeDot={{ r: 4.5 }}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                {trendLoading && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Spinner />
                  </div>
                )}
              </div>
            </div>

            <div className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-card">
              <h3 className="text-sm font-semibold text-content-primary">Severity Distribution</h3>
              <p className="text-xs text-content-tertiary mt-0.5">
                Share of alerts by severity — hover a slice for details.
              </p>
              <div className="relative h-56 mt-3" role="img" aria-label="Pie chart: share of alerts by severity">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={isMobile ? "72%" : "82%"}
                      innerRadius={isMobile ? "40%" : "48%"}
                      paddingAngle={2}
                      strokeWidth={0}
                      activeShape={renderActivePie}
                      onMouseEnter={(_, i) => setPieActive(i)}
                      onMouseLeave={() => setPieActive(null)}
                    >
                      {pieData.map((entry) => (
                        <Cell key={entry.name} fill={SEVERITY_COLORS[entry.name] || "rgb(var(--c-content-tertiary))"} />
                      ))}
                    </Pie>
                    <Tooltip content={(props: any) => <SeverityTooltip {...props} total={pieTotal} />} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-2xl font-bold text-content-primary tabular-nums">{pieTotal}</span>
                  <span className="text-[10px] uppercase tracking-wider text-content-tertiary">alerts</span>
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 mt-3">
                {pieData.map((entry, i) => {
                  const pct = pieTotal ? Math.round(((Number(entry.value) || 0) / pieTotal) * 100) : 0;
                  return (
                    <button
                      key={entry.name}
                      type="button"
                      onMouseEnter={() => setPieActive(i)}
                      onMouseLeave={() => setPieActive(null)}
                      className={`inline-flex items-center gap-1.5 text-xs text-content-secondary rounded-md px-1.5 py-0.5 transition ${
                        pieActive === i ? "bg-app-subtle" : ""
                      }`}
                    >
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ backgroundColor: SEVERITY_COLORS[entry.name] || "rgb(var(--c-content-tertiary))" }}
                      />
                      {entry.name.charAt(0) + entry.name.slice(1).toLowerCase()}
                      <span className="font-mono text-content-tertiary tabular-nums">{entry.value}</span>
                      <span className="font-mono text-content-tertiary tabular-nums">{pct}%</span>
                    </button>
                  );
                })}
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
                            style={{ width: `${Math.min(100, ((t.count || 0) / maxThreatCount) * 100)}%` }}
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
              <h3 className="text-sm font-semibold text-content-primary mb-1">Detections by Type</h3>
              <p className="text-xs text-content-tertiary mb-4">
                Counts by detection category — hover a bar for details.
              </p>
              {typeData.length === 0 ? (
                <p className="text-sm text-content-tertiary">No detections recorded yet.</p>
              ) : (
                <div className="h-56" role="img" aria-label="Bar chart: detection counts by alert type">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={typeData} margin={{ top: 16, right: 8, bottom: 0, left: -20 }}>
                      <CartesianGrid stroke="rgb(var(--c-line-subtle))" strokeDasharray="3 3" vertical={false} />
                      <XAxis
                        dataKey="name"
                        tick={{ fill: "rgb(var(--c-content-tertiary))", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        interval={0}
                      />
                      <YAxis
                        tick={{ fill: "rgb(var(--c-content-tertiary))", fontSize: 11 }}
                        allowDecimals={false}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip content={<TypeTooltip />} cursor={{ fill: "rgb(var(--c-app-subtle))" }} />
                      <Bar
                        dataKey="value"
                        name="Detections"
                        radius={[6, 6, 0, 0]}
                        maxBarSize={48}
                        label={{ position: "top", fontSize: 10, fill: "rgb(var(--c-content-tertiary))" }}
                      >
                        {typeData.map((d) => (
                          <Cell key={d.name} fill="rgb(var(--c-accent-primary))" />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          <div className="bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-card">
            <h3 className="text-sm font-semibold text-content-primary mb-4">Recent Detections</h3>
            {(overview.recent || []).length === 0 ? (
              <p className="text-sm text-content-tertiary">No recent alerts.</p>
            ) : (
              <div className="space-y-2">
                {(overview.recent || []).map((alert) => (
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
                        {formatDate(alert.created_at)}
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
                    {!explanation.contributions?.length ? (
                      <p className="text-xs text-content-tertiary">No strong signals found.</p>
                    ) : (
                      (explanation.contributions || []).map((c, idx) => (
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
                  {explanation.method && (
                    <p className="text-[11px] text-content-tertiary pt-1">{explanation.method}</p>
                  )}
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
                  {(benchmark.models || []).map((m) => (
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
                      {m.model_type && <p className="text-xs text-content-tertiary mb-2">{m.model_type}</p>}
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
