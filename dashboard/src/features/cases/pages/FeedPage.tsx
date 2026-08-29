import React, { useCallback, useEffect, useMemo, useState } from "react";
import { showSuccess } from "../../../utils/showSuccess";
import { useNavigate } from "react-router-dom";
import { PageHeader, Card, Button, SeverityBadge, StatusBadge, SkeletonTable, EmptyState, Term } from "../../../components/ui";
import { cn } from "../../../components/ui/Button";
import AnalystApi from "../../../api/analystApi";
import type { AnalystCase, Decision } from "../../../types/analyst";
import type { PaginatedResponse } from "../../../types/pagination";
import { getApiError } from "../../../utils/getApiError";

const PAGE_SIZE = 10;

/** Decision → calm status pill. Colour is alarm, so only "awaiting you" warms up. */
const DECISION_BADGE: Record<Decision, { tone: "success" | "warning" | "critical" | "neutral"; label: string }> = {
  pending: { tone: "warning", label: "Awaiting you" },
  approved: { tone: "success", label: "Approved" },
  declined: { tone: "neutral", label: "Declined" },
  reverted: { tone: "neutral", label: "Reverted" },
};

/** Defensive: the feed envelope is {data,total,…}, but tolerate a bare array. */
const asRows = (resp: PaginatedResponse<AnalystCase> | AnalystCase[] | undefined): AnalystCase[] => {
  if (Array.isArray(resp)) return resp;
  return resp?.data ?? [];
};

const FeedPage: React.FC = () => {
  const navigate = useNavigate();
  const [cases, setCases] = useState<AnalystCase[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkLoading, setBulkLoading] = useState<null | "approved" | "declined">(null);
  const [bulkResult, setBulkResult] = useState<string | null>(null);

  const loadFeed = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await AnalystApi.fetchFeed({ page, limit: PAGE_SIZE });
      setCases(asRows(resp));
      setTotal(resp?.total ?? 0);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load the decision feed"));
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  const pendingIdsOnPage = useMemo(() => cases.filter(c => c.decision === "pending").map(c => c.id), [cases]);
  const allPendingSelected = pendingIdsOnPage.length > 0 && pendingIdsOnPage.every(id => selected.has(id));

  const toggleOne = (id: number) => {
    setSelected(prev => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };
  const toggleAllPending = () => {
    setSelected(prev => {
      if (allPendingSelected) {
        const n = new Set(prev);
        pendingIdsOnPage.forEach(id => n.delete(id));
        return n;
      } else {
        const n = new Set(prev);
        pendingIdsOnPage.forEach(id => n.add(id));
        return n;
      }
    });
  };

  const handleBulk = async (decision: "approved" | "declined") => {
    if (selected.size === 0) return;
    setBulkLoading(decision);
    setBulkResult(null);
    setError(null);
    try {
      const res = await AnalystApi.bulkDecide(Array.from(selected), decision);
      const msg = `Bulk ${decision}: ${res.decided.length} decided, ${res.failed.length} failed`;
      if (res.failed.length > 0) {
        setBulkResult(msg + ". " + res.failed.map(f => `#${f.id}: ${f.reason}`).join("; "));
      } else {
        showSuccess(msg);
        setBulkResult(null);
      }
      setSelected(new Set());
      await loadFeed();
    } catch (e: any) {
      setError(getApiError(e, `Bulk ${decision} failed`));
    } finally {
      setBulkLoading(null);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Cases"
        description={
          <>
            Everything your analyst has surfaced — the story, the <Term>blast radius</Term>, and
            the <Term>decision</Term> each case is waiting on.
          </>
        }
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            {selected.size > 0 && (
              <>
                <span className="text-xs text-content-secondary">{selected.size} selected</span>
                <Button type="button" variant="primary" disabled={!!bulkLoading} onClick={() => handleBulk("approved")}>
                  {bulkLoading === "approved" ? "Approving…" : `Approve selected`}
                </Button>
                <Button type="button" variant="secondary" disabled={!!bulkLoading} onClick={() => handleBulk("declined")}>
                  {bulkLoading === "declined" ? "Declining…" : `Decline selected`}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>
              </>
            )}
            <Button type="button" variant="secondary" onClick={loadFeed}>
              Refresh
            </Button>
          </div>
        }
      />

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}
      {bulkResult && (
        <div className="px-4 py-3 rounded-lg bg-status-warning/10 border border-status-warning/30 text-sm text-content-primary">
          {bulkResult}
        </div>
      )}

      <Card padded={false} className="overflow-hidden">
        {loading ? (
          <SkeletonTable rows={6} cols={4} bare />
        ) : cases.length === 0 ? (
          <EmptyState
            title="No cases yet"
            description="When your analyst investigates something, it opens a case here. Head to Home and try “Simulate scenario.”"
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
                    <th scope="col" className="px-3 py-3.5 w-8">
                      <input type="checkbox" checked={allPendingSelected} onChange={toggleAllPending} aria-label="Select all pending" />
                    </th>
                    <th scope="col" className="px-5 py-3.5">Case</th>
                    <th scope="col" className="px-5 py-3.5 w-28">Severity</th>
                    <th scope="col" className="px-5 py-3.5 w-40">Decision</th>
                    <th scope="col" className="px-5 py-3.5 w-44">Opened</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-subtle text-sm">
                  {cases.map((c) => {
                    const badge = DECISION_BADGE[c.decision] ?? DECISION_BADGE.pending;
                    return (
                      <tr
                        key={c.id}

                        className={cn(
                          "hover:bg-app-subtle/50 transition-colors",
                          // SIGNAL: a pending decision is the row that needs
                          // you, so it carries the signal left edge (threat-item).
                          c.decision === "pending" && "threat-item"
                        )}
                      >
                        <td className="px-3 py-3.5">
                          {c.decision === "pending" ? (
                            <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggleOne(c.id)} onClick={(e) => e.stopPropagation()} aria-label={`Select case ${c.id}`} />
                          ) : null}
                        </td>
                        <td className="px-5 py-3.5 max-w-md cursor-pointer" onClick={() => navigate(`/case/${c.id}`)}>
                          <p className="text-content-primary font-medium truncate" title={c.analysis?.headline || c.title}>
                            {c.analysis?.headline || c.title}
                          </p>
                          {c.proposed_action && (
                            <p className="text-xs text-content-tertiary truncate mt-0.5">
                              <span className="font-mono">{c.proposed_action.action_type}</span> · {c.proposed_action.target}
                            </p>
                          )}
                        </td>
                        <td className="px-5 py-3.5 cursor-pointer" onClick={() => navigate(`/case/${c.id}`)}>
                          <SeverityBadge severity={c.priority} />
                        </td>
                        <td className="px-5 py-3.5 cursor-pointer" onClick={() => navigate(`/case/${c.id}`)}>
                          <StatusBadge tone={badge.tone} label={badge.label} />
                        </td>
                        <td className="px-5 py-3.5 text-xs text-content-tertiary whitespace-nowrap cursor-pointer" onClick={() => navigate(`/case/${c.id}`)}>
                          {c.created_at ? new Date(c.created_at).toLocaleString() : "-"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-between px-5 py-3.5 border-t border-line-subtle text-xs text-content-secondary gap-3">
              <span>
                Showing <span className="text-content-primary font-medium">{(page - 1) * PAGE_SIZE + 1}</span> -{" "}
                <span className="text-content-primary font-medium">{Math.min(page * PAGE_SIZE, total)}</span> of{" "}
                <span className="text-content-primary font-medium">{total}</span> cases
              </span>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1.5 bg-app-subtle hover:bg-line-bright border border-line-subtle text-content-secondary rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <span className="px-2 text-content-secondary font-medium">{page} / {totalPages}</span>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="px-3 py-1.5 bg-app-subtle hover:bg-line-bright border border-line-subtle text-content-secondary rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
};

export default FeedPage;
