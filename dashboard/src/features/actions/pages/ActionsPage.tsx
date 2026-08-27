import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ShieldAlert,
  RotateCcw,
  CheckCircle2,
  Lock,
  Search,
  ExternalLink,
} from "lucide-react";
import {
  PageHeader,
  Card,
  Button,
  StatusBadge,
  LoadingState,
  EmptyState,
} from "../../../components/ui";
import AnalystApi from "../../../api/analystApi";
import { getApiError } from "../../../utils/getApiError";
import { showError } from "../../../utils/showError";
import type { AnalystCase } from "../../../types/analyst";

const ActionsPage: React.FC = () => {
  const [cases, setCases] = useState<AnalystCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revertingId, setRevertingId] = useState<number | null>(null);
  const [search, setSearch] = useState("");

  const loadActions = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await AnalystApi.fetchFeed({ page: 1, limit: 50 });
      // Filter cases that have an approved or reverted action
      const actionCases = res.data.filter(
        (c) => c.decision === "approved" || c.decision === "reverted"
      );
      setCases(actionCases);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load containment actions"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadActions();
    localStorage.setItem("noctra_visited_actions", "1");
  }, []);

  const handleRevert = async (id: number) => {
    setRevertingId(id);
    try {
      const updated = await AnalystApi.revertCase(id);
      setCases((prev) => prev.map((c) => (c.id === id ? updated : c)));
    } catch (err: any) {
      showError(getApiError(err, "Could not revert action"));
    } finally {
      setRevertingId(null);
    }
  };

  const filtered = cases.filter((c) => {
    const term = search.toLowerCase();
    const action = c.proposed_action?.action_type || "";
    const target = c.proposed_action?.target || "";
    return (
      c.title.toLowerCase().includes(term) ||
      action.toLowerCase().includes(term) ||
      target.toLowerCase().includes(term)
    );
  });

  if (loading) return <LoadingState label="Loading containment actions log…" />;

  return (
    <div className="space-y-6 animate-fade-in bg-app-bg min-h-screen -m-6 p-6 sm:p-8">
      <PageHeader
        title="Actions Log"
        crumbs={[{ label: "Overview", to: "/" }, { label: "Actions" }]}
        description="Every decision you authorize is recorded here with a full audit reference and a one-click compensating reversal. NOCTRA records actions — it never executes them against your systems; your team stays in control."
      />

      {error && (
        <div
          role="alert"
          className="p-4 rounded-xl bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical font-medium"
        >
          {error}
        </div>
      )}

      {/* Filter / Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-app-surface p-4 rounded-2xl border border-line-subtle shadow-card">
        <div className="relative flex-1 w-full">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-content-tertiary" />
          <input
            type="text"
            placeholder="Filter by action type, target, or case title..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-app-subtle border border-line-subtle rounded-xl pl-10 pr-4 py-2 text-xs text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary font-medium"
          />
        </div>
        <div className="flex items-center gap-2 text-xs text-content-secondary font-medium shrink-0">
          <Lock size={14} className="text-status-success" />
          <span>Record-only SOAR · every action reversible</span>
        </div>
      </div>

      {/* Actions Table Card */}
      <Card padded={false} className="overflow-hidden border-line-subtle shadow-card bg-app-surface">
        {filtered.length === 0 ? (
          <div className="p-12 text-center">
            <EmptyState
              title="No recorded actions"
              description={
                search
                  ? "No actions match your filter criteria."
                  : "No actions have been recorded yet. Approve a recommended action on a case and it will appear here."
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-line-subtle bg-app-subtle/80 text-content-tertiary uppercase font-bold tracking-wider">
                  <th scope="col" className="px-5 py-3.5">Case & Title</th>
                  <th scope="col" className="px-5 py-3.5">Action Type</th>
                  <th scope="col" className="px-5 py-3.5">Target Asset</th>
                  <th scope="col" className="px-5 py-3.5">SOAR ID</th>
                  <th scope="col" className="px-5 py-3.5">Status</th>
                  <th scope="col" className="px-5 py-3.5 text-right">Reversibility</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-subtle text-content-secondary">
                {filtered.map((c) => {
                  const action = c.proposed_action;
                  const isApproved = c.decision === "approved";
                  const isReverted = c.decision === "reverted";

                  return (
                    <tr key={c.id} className="hover:bg-app-surface-raised/60 transition">
                      <td className="px-5 py-4 font-semibold text-content-primary">
                        <Link
                          to={`/case/${c.id}`}
                          className="hover:text-accent-primary flex items-center gap-1.5"
                        >
                          <span>Case #{c.id}</span>
                          <span className="font-normal text-content-tertiary truncate max-w-[200px]">
                            — {c.title}
                          </span>
                          <ExternalLink size={12} className="text-content-tertiary shrink-0" />
                        </Link>
                      </td>
                      <td className="px-5 py-4 font-mono font-bold text-accent-primary">
                        {action?.action_type || "ALERT_OPERATOR"}
                      </td>
                      <td className="px-5 py-4 font-mono text-content-secondary">
                        {action?.target || "System"}
                      </td>
                      <td className="px-5 py-4 font-mono text-content-tertiary">
                        {c.soar_action_id || `act_${c.id}`}
                      </td>
                      <td className="px-5 py-4">
                        <StatusBadge
                          tone={isApproved ? "success" : "neutral"}
                          label={isApproved ? "Recorded" : "Reverted"}
                        />
                      </td>
                      <td className="px-5 py-4 text-right">
                        {isApproved ? (
                          <Button
                            variant="secondary"
                            size="sm"
                            disabled={revertingId === c.id}
                            onClick={() => handleRevert(c.id)}
                            className="text-xs text-status-critical hover:bg-status-critical/10 hover:border-status-critical/30"
                          >
                            <RotateCcw size={13} className="mr-1" />
                            {revertingId === c.id ? "Reverting..." : "Revert"}
                          </Button>
                        ) : isReverted ? (
                          <span className="text-xs text-content-tertiary font-medium inline-flex items-center gap-1">
                            <CheckCircle2 size={13} className="text-status-success" />
                            Reverted
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};

export default ActionsPage;
