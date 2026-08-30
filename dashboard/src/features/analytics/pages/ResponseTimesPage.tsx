import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Info, EyeOff, Clock } from "lucide-react";
import apiClient from "../../../api/client";
import { cn } from "../../../components/ui";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  Select,
  SkeletonCard,
  StatCard,
  Badge,
} from "../../../components/ui";
import { useToast } from "../../../components/ui/Toast";
import { getApiError } from "../../../utils/getApiError";

/**
 * How long the loop actually takes, measured from recorded timestamps.
 *
 * This is what an SMB buyer benchmarks against, which is exactly why it used
 * to be invented: the previous board pack asserted a 2.5-hour MTTD, $50,000 of
 * cost avoidance and 120 analyst hours saved, none of them computed.
 *
 * Two things this page refuses to do: report a metric without saying how many
 * cases it came from, and imply that an unmeasurable number is simply absent.
 * Anything the system cannot measure is listed explicitly, with the reason.
 */

interface Metric {
  metric: string;
  measures: string;
  sample_size: number;
  median_minutes: number | null;
  p90_minutes: number | null;
  fastest_minutes?: number;
  slowest_minutes?: number;
  reliable: boolean;
  reason: string | null;
  caveat: string | null;
}

interface SourceCoverage {
  source: string;
  alerts: number;
  with_event_time: number;
  percent: number;
  note: string | null;
}

interface NotMeasured {
  metric: string;
  reason: string;
}

interface Report {
  window_days: number;
  cases_in_window: number;
  metrics: Metric[];
  open_backlog: { undecided_cases: number; oldest_undecided_minutes: number | null };
  event_time_coverage: SourceCoverage[];
  not_measured: NotMeasured[];
}

const TITLES: Record<string, string> = {
  time_to_detect: "Time to detect",
  time_to_triage: "Time to triage",
  time_to_decision: "Time to decision",
  time_to_contain: "Time to contain",
};

const humanise = (key: string): string =>
  key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** Minutes are unreadable past an hour; scale the unit to the magnitude. */
const duration = (minutes: number | null): string => {
  if (minutes === null) return "—";
  if (minutes < 1) return "<1 min";
  if (minutes < 90) return `${Math.round(minutes)} min`;
  const hours = minutes / 60;
  if (hours < 48) return `${hours.toFixed(1)} h`;
  return `${(hours / 24).toFixed(1)} d`;
};

const MetricCard: React.FC<{ metric: Metric }> = ({ metric }) => (
  <Card className="p-5 space-y-3">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-sm font-bold font-display text-content-primary">
          {TITLES[metric.metric] ?? humanise(metric.metric)}
        </h2>
        <p className="text-xs text-content-tertiary mt-0.5">{metric.measures}</p>
      </div>
      <Badge
        className={
          metric.reliable
            ? "bg-status-success/10 text-status-success border-status-success/30"
            : "bg-app-subtle text-content-tertiary border-line-subtle"
        }
      >
        n={metric.sample_size}
      </Badge>
    </div>

    {metric.median_minutes === null ? (
      <p className="text-xs text-content-secondary">
        Nothing measured yet — {metric.reason}.
      </p>
    ) : (
      <>
        <div className="flex items-baseline gap-4">
          <div>
            <p className="text-3xl font-bold tabular-nums leading-none text-content-primary">
              {duration(metric.median_minutes)}
            </p>
            <p className="tech-label text-content-tertiary mt-1">median</p>
          </div>
          <div>
            <p className="text-lg font-bold tabular-nums leading-none text-content-secondary">
              {duration(metric.p90_minutes)}
            </p>
            <p className="tech-label text-content-tertiary mt-1">p90</p>
          </div>
        </div>

        {metric.fastest_minutes != null && metric.slowest_minutes != null && (
          <p className="text-xs text-content-tertiary tabular-nums">
            Range {duration(metric.fastest_minutes)} – {duration(metric.slowest_minutes)}
          </p>
        )}

        {!metric.reliable && metric.reason && (
          <p className="text-xs text-status-warning">{metric.reason}.</p>
        )}
      </>
    )}

    {metric.caveat && (
      <div className="flex items-start gap-2 border-t border-line-subtle pt-2.5">
        <Info size={13} className="text-content-tertiary shrink-0 mt-px" aria-hidden />
        <p className="text-xs text-content-secondary">{metric.caveat}</p>
      </div>
    )}
  </Card>
);

export default function ResponseTimesPage() {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [windowDays, setWindowDays] = useState(30);
  const { push } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/exec-risk/response-times?window_days=${windowDays}`);
      setReport(res.data as Report);
    } catch (e) {
      setReport(null);
      push(getApiError(e, "Could not load response times"), "error");
    } finally {
      setLoading(false);
    }
  }, [windowDays, push]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Response times"
        description="How long the loop takes, measured from recorded timestamps rather than targets."
        actions={
          <div className="flex items-center gap-2">
            <Select
              inline
              label="Window"
              value={String(windowDays)}
              onChange={(e) => setWindowDays(Number(e.target.value))}
              options={[
                { value: "7", label: "7 days" },
                { value: "30", label: "30 days" },
                { value: "90", label: "90 days" },
              ]}
            />
            <Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading}>
              <RefreshCw size={13} className="mr-1.5" /> Refresh
            </Button>
          </div>
        }
      />

      {loading ? (
        <SkeletonCard />
      ) : !report ? (
        <EmptyState
          title="Response times unavailable"
          description="The metrics could not be loaded. This is a failure, not an absence of activity."
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Cases in window" value={report.cases_in_window} />
            <StatCard label="Awaiting decision" value={report.open_backlog.undecided_cases} />
            <StatCard
              label="Oldest undecided"
              value={duration(report.open_backlog.oldest_undecided_minutes)}
            />
          </div>

          {report.cases_in_window === 0 ? (
            <EmptyState
              icon={<Clock size={20} />}
              title="No cases in this window"
              description={`Nothing has been triaged in the last ${report.window_days} days, so there is nothing to time. This is a real zero, not a failure.`}
            />
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {report.metrics.map((m) => (
                <MetricCard key={m.metric} metric={m} />
              ))}
            </div>
          )}

          {/* Which connectors actually supply an event time. A source at 0%
              means its timestamp mapping is wrong or the provider sends
              nothing — the reason detection latency covers only a subset. */}
          {report.event_time_coverage.length > 0 && (
            <Card className="p-5">
              <h2 className="text-sm font-bold font-display text-content-primary mb-1">
                Event-time coverage by source
              </h2>
              <p className="text-xs text-content-tertiary mb-3">
                Detection latency can only be measured for alerts whose source reports
                when the event happened.
              </p>
              <div className="space-y-2">
                {report.event_time_coverage.map((c) => (
                  <div
                    key={c.source}
                    className="flex items-start justify-between gap-3 flex-wrap border-b border-line-subtle last:border-0 pb-2 last:pb-0"
                  >
                    <div className="min-w-0">
                      <span className="text-sm font-medium text-content-primary">
                        {c.source}
                      </span>
                      {c.note && (
                        <p className="text-xs text-status-warning mt-0.5">{c.note}</p>
                      )}
                    </div>
                    <span
                      className={cn(
                        "text-xs font-mono tabular-nums shrink-0",
                        c.percent === 0 ? "text-status-critical" : "text-content-secondary",
                      )}
                    >
                      {c.with_event_time}/{c.alerts} ({c.percent}%)
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {report.not_measured.length > 0 && (
            <Card className="p-5">
              <div className="flex items-center gap-1.5 mb-3">
                <EyeOff size={14} className="text-content-tertiary" aria-hidden />
                <h2 className="text-sm font-bold font-display text-content-primary">
                  Not measured ({report.not_measured.length})
                </h2>
              </div>
              <ul className="space-y-2">
                {report.not_measured.map((n) => (
                  <li key={n.metric} className="text-xs">
                    <span className="font-medium text-content-primary">
                      {humanise(n.metric)}
                    </span>
                    <span className="text-content-secondary"> — {n.reason}</span>
                  </li>
                ))}
              </ul>
              <p className="text-[11px] text-content-tertiary mt-3">
                These are reported as unmeasurable rather than estimated. A figure here
                would be a guess presented as a result.
              </p>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
