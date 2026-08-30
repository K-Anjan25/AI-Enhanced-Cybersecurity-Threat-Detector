import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { AlertTriangle, RefreshCw } from "lucide-react";
import apiClient from "../../../api/client";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  RawData,
  SkeletonCard,
  StatCard,
  Badge,
  SeverityBadge,
} from "../../../components/ui";
import { useToast } from "../../../components/ui/Toast";
import { getApiError } from "../../../utils/getApiError";

/**
 * Capability pages that are read-oriented enough to share one shell.
 *
 * These used to be a routing shim that dumped the operator into a tabbed
 * "Labs" hub showing raw JSON. Each route now fetches its own data and renders
 * it as records, with the payload available behind a disclosure rather than as
 * the primary interface.
 *
 * A route is only listed here if its backend computes from real rows. Anything
 * that fabricated data was removed rather than given a nicer wrapper.
 */

interface Feed {
  /** Human name for the capability. */
  title: string;
  description: string;
  /** Endpoints to pull, in display order. `label` heads each section. */
  sources: { label: string; path: string }[];
}

const FEEDS: Record<string, Feed> = {
  "/ztna": {
    title: "Zero trust access",
    description: "Network segments and the policies governing traffic between them.",
    sources: [
      { label: "Segments", path: "/ztna/segments" },
      { label: "Policies", path: "/ztna/policies" },
    ],
  },
  "/vulns": {
    title: "Vulnerabilities",
    description: "Known vulnerabilities across your assets, ranked by risk.",
    sources: [
      { label: "Risk summary", path: "/vulns/risk/summary" },
      { label: "Vulnerabilities", path: "/vulns" },
    ],
  },
  "/cspm": {
    title: "Cloud posture",
    description: "Connected cloud accounts and the misconfigurations found in them.",
    sources: [
      { label: "Accounts", path: "/cspm/accounts" },
      { label: "Violations", path: "/cspm/violations" },
    ],
  },
  "/sbom": {
    title: "Software supply chain",
    description: "Software bills of materials and the risk carried by your dependencies.",
    sources: [
      { label: "SBOMs", path: "/sbom/" },
      { label: "Risks", path: "/sbom/risks" },
    ],
  },
  "/deception": {
    title: "Deception",
    description: "Decoys placed to catch lateral movement, and what has touched them.",
    sources: [
      { label: "Honeypots", path: "/deception/honeypots" },
      { label: "Decoy alerts", path: "/deception/alerts" },
    ],
  },
  "/forensics": {
    title: "Forensics",
    description: "Evidence collected during investigations.",
    sources: [
      { label: "Cases", path: "/forensics/cases" },
      { label: "Artifacts", path: "/forensics/artifacts" },
    ],
  },
  "/itdr": {
    title: "Identity threats",
    description: "Identity-based attacks and risky sign-in activity.",
    sources: [
      { label: "Threats", path: "/itdr/threats" },
      { label: "Risky sign-ins", path: "/itdr/risky-signins" },
    ],
  },
  "/tip": {
    title: "Threat intel platform",
    description: "Indicators and feeds NOCTRA enriches alerts against.",
    sources: [{ label: "Feeds", path: "/tip/feeds" }],
  },
  "/threat-intel": {
    title: "Threat intel",
    description: "Enrichment provider status and cached lookups.",
    sources: [{ label: "Providers", path: "/threat-intel/status" }],
  },
  "/attack-navigator": {
    title: "ATT&CK navigator",
    description: "Technique activity mapped onto the ATT&CK matrix.",
    sources: [
      { label: "Heatmap", path: "/attack/heatmap" },
    ],
  },
  "/compliance-continuous": {
    title: "Continuous compliance",
    description: "Control status evaluated continuously rather than at audit time.",
    sources: [{ label: "Controls", path: "/compliance-continuous/controls" }],
  },
  "/exec-risk": {
    title: "Executive risk",
    description: "The board-level view: risk metrics and programme return.",
    sources: [
      { label: "Metrics", path: "/exec-risk/metrics" },
      { label: "ROI", path: "/exec-risk/roi" },
    ],
  },
  "/ai-agent": {
    title: "AI agent",
    description: "The autonomous investigator's status and tool use.",
    sources: [{ label: "Status", path: "/ai-agent/status" }],
  },
};

const matchFeed = (path: string): [string, Feed] | undefined => {
  const key = Object.keys(FEEDS).find((p) => path === p || path.startsWith(`${p}/`));
  return key ? [key, FEEDS[key]] : undefined;
};

const TITLE_KEYS = ["title", "name", "hostname", "cve_id", "technique_id", "indicator", "id"];
const DETAIL_KEYS = ["description", "detail", "summary", "reason", "recommendation", "query", "status"];

const pick = (row: Record<string, unknown>, keys: string[]): string | undefined => {
  for (const k of keys) {
    const v = row[k];
    if (typeof v === "string" && v.trim()) return v;
    if (typeof v === "number") return String(v);
  }
  return undefined;
};

/** Render one API response: a list of records, a scalar summary, or nothing. */
const Section: React.FC<{ label: string; data: unknown; error?: string | null }> = ({
  label,
  data,
  error,
}) => {
  const rows = Array.isArray(data) ? data : null;
  const isObject = !rows && data !== null && typeof data === "object";
  const scalars = isObject
    ? Object.entries(data as Record<string, unknown>).filter(
        ([, v]) => typeof v === "number" || typeof v === "string" || typeof v === "boolean",
      )
    : [];

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-2 mb-3">
        <h2 className="text-sm font-bold font-display text-content-primary">{label}</h2>
        {rows && (
          <Badge className="bg-app-subtle text-content-tertiary border-line-subtle">
            {rows.length}
          </Badge>
        )}
      </div>

      {error ? (
        <div className="flex items-start gap-2 text-xs text-status-critical">
          <AlertTriangle size={14} className="shrink-0 mt-px" aria-hidden />
          <span>
            Could not load this section — {error}. This is a failure, not an empty result.
          </span>
        </div>
      ) : rows ? (
        rows.length === 0 ? (
          <p className="text-xs text-content-tertiary">Nothing recorded yet.</p>
        ) : (
          <div className="space-y-2">
            {rows.slice(0, 50).map((row, i) => {
              const r = (row ?? {}) as Record<string, unknown>;
              const title = pick(r, TITLE_KEYS) ?? `Record ${i + 1}`;
              const detail = pick(r, DETAIL_KEYS);
              const severity = typeof r.severity === "string" ? r.severity : undefined;
              return (
                <div
                  key={i}
                  className="border-b border-line-subtle last:border-0 pb-2 last:pb-0 text-xs"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    {severity && <SeverityBadge severity={severity} />}
                    <span className="font-medium text-content-primary">{title}</span>
                  </div>
                  {detail && detail !== title && (
                    <p className="text-content-secondary mt-0.5">{detail}</p>
                  )}
                </div>
              );
            })}
            {rows.length > 50 && (
              <p className="text-[11px] text-content-tertiary pt-1">
                Showing the first 50 of {rows.length}.
              </p>
            )}
          </div>
        )
      ) : scalars.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-3">
          {scalars.slice(0, 9).map(([k, v]) => (
            <StatCard key={k} label={k.replace(/_/g, " ")} value={String(v)} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-content-tertiary">No data returned.</p>
      )}

      {!error && <RawData value={data} />}
    </Card>
  );
};

export default function ModulePage() {
  const path = useLocation().pathname;
  const matched = useMemo(() => matchFeed(path), [path]);
  const [results, setResults] = useState<
    { label: string; data: unknown; error: string | null }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const { push } = useToast();

  const feed = matched?.[1];

  const load = useCallback(async () => {
    if (!feed) {
      setLoading(false);
      return;
    }
    setLoading(true);
    const settled = await Promise.allSettled(feed.sources.map((s) => apiClient.get(s.path)));
    // A rejected source keeps its error. Rendering it as empty would tell the
    // operator "there is nothing here" when the truth is "we do not know".
    const next = feed.sources.map((s, i) => {
      const r = settled[i];
      return r.status === "fulfilled"
        ? { label: s.label, data: r.value.data, error: null }
        : { label: s.label, data: null, error: getApiError(r.reason, "Could not load") };
    });
    setResults(next);
    if (settled.every((r) => r.status === "rejected")) {
      const first = settled[0];
      push(
        getApiError(first.status === "rejected" ? first.reason : null, "Could not load this view"),
        "error",
      );
    }
    setLoading(false);
  }, [feed, push]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!feed) {
    return (
      <EmptyState
        title="Not available"
        description={`There is no view for ${path}. It may have been removed.`}
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={feed.title}
        description={feed.description}
        actions={
          <Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading}>
            <RefreshCw size={13} className="mr-1.5" /> Refresh
          </Button>
        }
      />
      {loading ? (
        <SkeletonCard />
      ) : (
        results.map((r) => (
          <Section key={r.label} label={r.label} data={r.data} error={r.error} />
        ))
      )}
    </div>
  );
}
