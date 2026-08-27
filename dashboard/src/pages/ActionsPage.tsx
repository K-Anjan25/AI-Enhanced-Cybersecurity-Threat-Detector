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
} from "../components/ui";
import AnalystApi from "../api/analystApi";
import type { AnalystCase } from "../types/analyst";

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
      setError(err?.detail || "Failed to load containment actions");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadActions();
  }, []);

  const handleRevert = async (id: number) => {
    setRevertingId(id);
    try {
      const updated = await AnalystApi.revertCase(id);
      setCases((prev) => prev.map((c) => (c.id === id ? updated : c)));
    } catch (err: any) {
      alert(err?.detail || "Could not revert action");
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
        title="Containment Actions & Reversibility Log"
        crumbs={[{ label: "Overview", to: "/" }, { label: "Actions" }]}
        description="All executed threat containment actions are recorded with complete audit references and 1-click reversal controls."
      />

      {error && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-600 font-medium">
          {error}
        </div>
      )}

      {/* Filter / Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-white p-4 rounded-2xl border border-line-subtle shadow-card">
        <div className="relative flex-1 w-full">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Filter by action type, target, or incident title..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-10 pr-4 py-2 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-blue-500 font-medium"
          />
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500 font-medium shrink-0">
          <Lock size={14} className="text-emerald-600" />
          <span>Record-only SOAR • 100% Reversible</span>
        </div>
      </div>

      {/* Actions Table Card */}
      <Card padded={false} className="overflow-hidden border-line-subtle shadow-card bg-white">
        {filtered.length === 0 ? (
          <div className="p-12 text-center">
            <EmptyState
              title="No containment actions found"
              description={
                search
                  ? "No actions match your filter criteria."
                  : "NOCTRA has not executed any containment actions yet."
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/80 text-slate-400 uppercase font-bold tracking-wider">
                  <th className="px-5 py-3.5">Case & Title</th>
                  <th className="px-5 py-3.5">Action Type</th>
                  <th className="px-5 py-3.5">Target Asset</th>
                  <th className="px-5 py-3.5">SOAR ID</th>
                  <th className="px-5 py-3.5">Status</th>
                  <th className="px-5 py-3.5 text-right">Reversibility</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {filtered.map((c) => {
                  const action = c.proposed_action;
                  const isApproved = c.decision === "approved";
                  const isReverted = c.decision === "reverted";

                  return (
                    <tr key={c.id} className="hover:bg-slate-50/60 transition">
                      <td className="px-5 py-4 font-semibold text-slate-900">
                        <Link
                          to={`/case/${c.id}`}
                          className="hover:text-blue-600 flex items-center gap-1.5"
                        >
                          <span>Case #{c.id}</span>
                          <span className="font-normal text-slate-500 truncate max-w-[200px]">
                            — {c.title}
                          </span>
                          <ExternalLink size={12} className="text-slate-400 shrink-0" />
                        </Link>
                      </td>
                      <td className="px-5 py-4 font-mono font-bold text-blue-600">
                        {action?.action_type || "ALERT_OPERATOR"}
                      </td>
                      <td className="px-5 py-4 font-mono text-slate-800">
                        {action?.target || "System"}
                      </td>
                      <td className="px-5 py-4 font-mono text-slate-400">
                        {c.soar_action_id || `act_${c.id}`}
                      </td>
                      <td className="px-5 py-4">
                        <StatusBadge
                          tone={isApproved ? "success" : "neutral"}
                          label={isApproved ? "Executed" : "Reverted"}
                        />
                      </td>
                      <td className="px-5 py-4 text-right">
                        {isApproved ? (
                          <Button
                            variant="secondary"
                            size="sm"
                            disabled={revertingId === c.id}
                            onClick={() => handleRevert(c.id)}
                            className="text-xs text-red-600 hover:bg-red-50 hover:border-red-200"
                          >
                            <RotateCcw size={13} className="mr-1" />
                            {revertingId === c.id ? "Reverting..." : "Revert Action"}
                          </Button>
                        ) : isReverted ? (
                          <span className="text-xs text-slate-400 font-medium inline-flex items-center gap-1">
                            <CheckCircle2 size={13} className="text-emerald-500" />
                            Reversed
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
