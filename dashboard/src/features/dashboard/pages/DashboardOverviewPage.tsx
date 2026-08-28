import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  AreaChart,
  Area,
} from "recharts";
import AnalyticsApi from "../../../api/analyticsApi";
import { fetchAlerts } from "../../../api/alertApi";
import { fetchSoarActions } from "../../../api/soarApi";
import { fetchIncidents } from "../../../api/incidentApi";
import {
  StatCard,
  Card,
  CardHeader,
  SeverityBadge,
  StatusBadge,
  Skeleton,
  SkeletonChart,
  SkeletonStatCard,
  EmptyState,
  PageHeader,
  Button,
  Term,
} from "../../../components/ui";
import type { OverviewStats, TopThreat, TrendPoint } from "../../../types/analytics";
import { getApiError } from "../../../utils/getApiError";
import { CHART_TOOLTIP_STYLE } from "../../../components/ui/chartTokens";

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

const DashboardOverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<OverviewStats>(EMPTY_OVERVIEW);
  const [threats, setThreats] = useState<TopThreat[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [openCases, setOpenCases] = useState(0);
  const [soarActions, setSoarActions] = useState(0);
  const [liveAlerts, setLiveAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [ov, th, tr, incidents, soar, alerts] = await Promise.all([
          AnalyticsApi.getOverview(),
          AnalyticsApi.getTopThreats(10),
          AnalyticsApi.getAlertTrends(7),
          fetchIncidents({ page: 1, limit: 1 }),
          fetchSoarActions({ page: 1, limit: 1 }),
          fetchAlerts(),
        ]);
        if (cancelled) return;
        setOverview(ov || EMPTY_OVERVIEW);
        setThreats(th || []);
        setTrend(tr?.trend || []);
        setOpenCases(incidents?.total ?? 0);
        setSoarActions(soar?.total ?? 0);
        const alertPayload: any = alerts as any;
        const list = Array.isArray(alertPayload)
          ? alertPayload
          : alertPayload?.items || [];
        setLiveAlerts(list);
      } catch (err: any) {
        if (!cancelled) setError(getApiError(err, "Failed to load overview data"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    const interval = setInterval(load, 60000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5">
              <Skeleton className="h-7 w-44" />
              <Skeleton className="h-5 w-24 rounded-full" />
            </div>
            <Skeleton className="h-3.5 w-80 max-w-full mt-2" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-9 w-28 rounded-lg" />
            <Skeleton className="h-9 w-32 rounded-full" />
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonStatCard key={i} />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <SkeletonChart className="lg:col-span-2 h-80" />
          <SkeletonChart className="h-80" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonStatCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  const maxThreatCount =
    threats.reduce((m, t) => Math.max(m, t.count || 0), 0) || 1;

  const criticalAlerts = liveAlerts
    .filter((a) => String(a.severity || a.risk || "").toUpperCase() === "CRITICAL")
    .slice(0, 5);

  const kpis = [
    {
      label: "Total Alerts",
      value: overview.total,
      hint: "All-time detections",
      tone: "default" as const,
      onClick: () => navigate("/alerts"),
    },
    {
      label: "Critical",
      value: overview.critical,
      hint: "Require immediate attention",
      tone: "critical" as const,
      onClick: () => navigate("/alerts"),
    },
    {
      label: "High",
      value: overview.high,
      hint: "Escalate & investigate",
      tone: "warning" as const,
      onClick: () => navigate("/alerts"),
    },
    {
      label: "Open Incidents",
      value: openCases,
      hint: "Active case load",
      tone: "accent" as const,
      onClick: () => navigate("/incidents"),
    },
    {
      label: "SOAR Executions",
      value: soarActions,
      hint: "Automated responses",
      tone: "success" as const,
      onClick: () => navigate("/soar"),
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header — shared PageHeader component (system conformance pass) */}
      <PageHeader
        title="SOC Cockpit"
        badge={<StatusBadge tone="success" label="Operational" />}
        description="Live security posture across the organization. Data refreshes automatically."
        actions={
          <>
            <Button variant="secondary" onClick={() => navigate("/logs")}>
              Upload Logs
            </Button>
            <Button variant="primary" onClick={() => navigate("/incidents")}>
              New Incident
            </Button>
          </>
        }
      />

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} onClick={kpi.onClick} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter") kpi.onClick?.(); }}>
            <StatCard label={kpi.label} value={kpi.value} hint={kpi.hint} tone={kpi.tone} className="hover:bg-app-surface-raised transition-colors cursor-pointer h-full" />
          </div>
        ))}
      </div>

      {/* Trend + top threats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader title="Alert Trend (7 days)" description="Detection volume by severity" />
          <div className="h-64 mt-4" role="img" aria-label="Area chart: detection volume by severity over the last 7 days">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend} margin={{ top: 5, right: 10, bottom: 5, left: -20 }}>
                <defs>
                  <linearGradient id="gTotal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#9d7cff" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#9d7cff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgb(var(--c-line-subtle))" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fill: "rgb(var(--c-content-tertiary))", fontSize: 11 }} />
                <YAxis tick={{ fill: "rgb(var(--c-content-tertiary))", fontSize: 11 }} allowDecimals={false} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Area type="monotone" dataKey="total" stroke="#9d7cff" strokeWidth={2} fill="url(#gTotal)" />
                <Line type="monotone" dataKey="critical" stroke="#f26d6d" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader title="Top Threats" description="Most frequent detection patterns" />
          <div className="mt-4 space-y-3">
            {threats.length === 0 ? (
              <EmptyState title="No threat patterns yet" description="Threats will appear as detections are analyzed." />
            ) : (
              threats.slice(0, 6).map((t, idx) => {
                const pct = Math.round(((t.count || 0) / maxThreatCount) * 100);
                return (
                  <div key={idx} className="flex items-center gap-3">
                    <span className="w-5 text-xs font-mono text-content-tertiary">{idx + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-content-primary truncate">{t.threat}</p>
                      <div className="h-1.5 bg-app-subtle rounded-full mt-1 overflow-hidden">
                        <div className="h-full bg-accent-primary rounded-full" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                    <span className="text-xs font-mono text-content-secondary shrink-0">{t.count}</span>
                  </div>
                );
              })
            )}
          </div>
        </Card>
      </div>

      {/* Live critical alerts */}
      <Card>
        <CardHeader
          title="Critical Alerts"
          description="Highest-priority detections needing triage"
          action={
            <Link to="/alerts" className="text-xs font-semibold text-accent-primary hover:text-accent-secondary transition">
              View all alerts &rarr;
            </Link>
          }
        />
        <div className="mt-3">
          {criticalAlerts.length === 0 ? (
            <EmptyState title="No critical alerts right now" description="Critical detections will appear here in real time." />
          ) : (
            <div className="space-y-2">
              {criticalAlerts.map((alert: any) => (
                <Link
                  key={alert.id}
                  to="/alerts"
                  className="flex items-center justify-between gap-4 px-4 py-3 rounded-lg bg-app-bg border border-line-subtle hover:border-status-critical/40 transition group"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-content-primary truncate font-mono text-xs group-hover:text-accent-primary transition">
                      {alert.message || alert.raw_log || "Critical detection"}
                    </p>
                    <p className="text-xs text-content-tertiary mt-0.5">
                      {alert.source_ip || alert.source || "Unknown source"}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {alert.mitre_technique_id && (
                      <span className="hidden sm:inline-flex px-2 py-0.5 rounded text-xs font-mono bg-app-subtle text-content-secondary border border-line-subtle">
                        <Term mono>{alert.mitre_technique_id}</Term>
                      </span>
                    )}
                    <SeverityBadge severity="CRITICAL" />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* Quick actions */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Threat Alerts", desc: "Review & triage detections", path: "/alerts", icon: "ALT" },
          { label: "Incidents", desc: "Manage investigation cases", path: "/incidents", icon: "INC" },
          { label: "Entity Graph", desc: "Explore attack relationships", path: "/entities", icon: "ENT" },
          { label: "SOAR Automation", desc: "Run & evaluate playbooks", path: "/soar", icon: "SOA" },
        ].map((q) => (
          <Link
            key={q.label}
            to={q.path} className="bg-app-surface border border-line-subtle rounded-2xl p-5 shadow-card hover:bg-app-surface-raised hover:border-line-bright transition group"
          >
            <span className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-accent-primary/10 text-accent-primary font-bold text-xs mb-3 group-hover:bg-accent-primary/20 transition">
              {q.icon}
            </span>
            <p className="text-sm font-semibold text-content-primary">{q.label}</p>
            <p className="text-xs text-content-tertiary mt-0.5">{q.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
};

export default DashboardOverviewPage;
