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
import AnalyticsApi from "../api/analyticsApi";
import type { OverviewStats, TopThreat, TrendPoint } from "../types/analytics";

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

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "#f87171",
  HIGH: "#fb923c",
  MEDIUM: "#fbbf24",
  LOW: "#34d399",
};

const AIAnalyticsPage: React.FC = () => {
  const [overview, setOverview] = useState<OverviewStats>(EMPTY_OVERVIEW);
  const [threats, setThreats] = useState<TopThreat[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        if (!cancelled) setError(err?.detail || "Failed to load analytics data");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const kpis = [
    { label: "Total Alerts", value: overview.total, color: "text-content-primary" },
    { label: "Critical", value: overview.critical, color: "text-status-critical" },
    { label: "High", value: overview.high, color: "text-orange-400" },
    { label: "Medium", value: overview.medium, color: "text-status-warning" },
    { label: "Low", value: overview.low, color: "text-status-success" },
  ];

  const pieData = [
    { name: "CRITICAL", value: overview.severity_distribution?.CRITICAL || 0 },
    { name: "HIGH", value: overview.severity_distribution?.HIGH || 0 },
    { name: "MEDIUM", value: overview.severity_distribution?.MEDIUM || 0 },
    { name: "LOW", value: overview.severity_distribution?.LOW || 0 },
  ];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-content-primary">AI Analytics</h1>
        <p className="text-sm text-content-secondary mt-1">
          Aggregated detection telemetry from the AI threat engine.
        </p>
      </header>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="p-6 bg-app-surface border border-line-subtle rounded-xl text-sm text-content-tertiary">
          Loading analytics...
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {kpis.map((kpi) => (
              <div
                key={kpi.label}
                className="bg-app-surface border border-line-subtle rounded-xl p-5 shadow-sm"
              >
                <p className="text-xs font-medium uppercase tracking-wider text-content-tertiary">
                  {kpi.label}
                </p>
                <p className={`text-3xl font-bold mt-2 ${kpi.color}`}>{kpi.value}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-app-surface border border-line-subtle rounded-xl p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-content-primary">Alert Trend (7 days)</h3>
              <div className="h-64 mt-4">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend} margin={{ top: 5, right: 10, bottom: 5, left: -20 }}>
                    <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
                    <YAxis tick={{ fill: "#64748b", fontSize: 11 }} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{
                        background: "#111827",
                        border: "1px solid #334155",
                        borderRadius: 8,
                        color: "#f1f5f9",
                      }}
                    />
                    <Line type="monotone" dataKey="total" stroke="#22d3ee" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="critical" stroke="#f87171" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="high" stroke="#fb923c" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="bg-app-surface border border-line-subtle rounded-xl p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-content-primary">Severity Distribution</h3>
              <div className="h-64 mt-4">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      label={(entry: any) => `${entry.name}: ${entry.value}`}
                    >
                      {pieData.map((entry) => (
                        <Cell key={entry.name} fill={SEVERITY_COLORS[entry.name] || "#64748b"} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "#111827",
                        border: "1px solid #334155",
                        borderRadius: 8,
                        color: "#f1f5f9",
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-app-surface border border-line-subtle rounded-xl p-6 shadow-sm">
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

            <div className="bg-app-surface border border-line-subtle rounded-xl p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-content-primary mb-4">Detections by Type</h3>
              {Object.keys(overview.by_type || {}).length === 0 ? (
                <p className="text-sm text-content-tertiary">No detections recorded yet.</p>
              ) : (
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={Object.entries(overview.by_type || {}).map(([name, value]) => ({ name, value }))}>
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#64748b", fontSize: 11 }} allowDecimals={false} />
                      <Tooltip
                        contentStyle={{
                          background: "#111827",
                          border: "1px solid #334155",
                          borderRadius: 8,
                          color: "#f1f5f9",
                        }}
                      />
                      <Bar dataKey="value" fill="#22d3ee" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          <div className="bg-app-surface border border-line-subtle rounded-xl p-6 shadow-sm">
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
                          color: SEVERITY_COLORS[alert.severity] || "#94a3b8",
                          backgroundColor: `${SEVERITY_COLORS[alert.severity] || "#94a3b8"}22`,
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
        </>
      )}
    </div>
  );
};

export default AIAnalyticsPage;
