import React, { useCallback, useEffect, useState } from "react";
import SoarApi from "../api/soarApi";
import type { SoarAction } from "../types/soar";
import {
  PageHeader,
  Card,
  Select,
  SkeletonTable,
  EmptyState,
} from "../components/ui";

const PAGE_SIZE = 10;

const statusBadge: Record<string, string> = {
  pending: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  executing: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  executed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  failed: "bg-red-500/15 text-red-400 border-red-500/30",
  skipped: "bg-app-subtle text-content-secondary border-line-subtle",
};

const severityBadge: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  medium: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  high: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  critical: "bg-red-500/15 text-red-400 border-red-500/30",
};

const SoarPage: React.FC = () => {
  const [actions, setActions] = useState<SoarAction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [evalMessage, setEvalMessage] = useState<string>("");
  const [evalType, setEvalType] = useState<string>("system_log");
  const [evalResult, setEvalResult] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  const [triggerId, setTriggerId] = useState<string>("");
  const [triggerResult, setTriggerResult] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);

  const loadActions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await SoarApi.fetchActions({ page, limit: PAGE_SIZE });
      setActions(response.data);
      setTotal(response.total);
    } catch (err: any) {
      setError(err?.detail || "Failed to load automation actions");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    loadActions();
  }, [loadActions]);

  const handleEvaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    setEvaluating(true);
    setEvalResult(null);
    setError(null);
    try {
      const result = await SoarApi.evaluateAlert({
        alert_type: evalType,
        message: evalMessage,
      });
      setEvalResult(
        result.count === 0
          ? "No actions would fire for this input."
          : `${result.count} action(s) would fire: ${result.actions
              .map((a) => (a as any).action_type)
              .filter(Boolean)
              .join(", ")}`
      );
    } catch (err: any) {
      setError(err?.detail || "Evaluation failed");
    } finally {
      setEvaluating(false);
    }
  };

  const handleTrigger = async (e: React.FormEvent) => {
    e.preventDefault();
    const alertId = Number(triggerId);
    if (!Number.isInteger(alertId) || alertId <= 0) {
      setTriggerResult("Enter a valid numeric alert ID.");
      return;
    }
    setTriggering(true);
    setTriggerResult(null);
    setError(null);
    try {
      const result = await SoarApi.triggerForAlert(alertId);
      setTriggerResult(
        result.count === 0
          ? `Alert #${alertId}: no actions executed. Check that it matches active rules.`
          : `Alert #${alertId}: ${result.count} action(s) executed (${result.executed
              .map((a) => (a as any).action_type)
              .filter(Boolean)
              .join(", ")}).`
      );
      setPage(1);
      await loadActions();
    } catch (err: any) {
      setTriggerResult(null);
      setError(err?.detail || "Trigger failed");
    } finally {
      setTriggering(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="SOAR Automation"
        description="Review automated response actions and test rule matching before they run."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <h2 className="text-lg font-semibold text-content-primary tracking-tight">Dry-run evaluator</h2>
          <p className="text-xs text-content-tertiary mt-0.5 mb-4">
            Test a log line against active rules without executing any action.
          </p>
          <form onSubmit={handleEvaluate} className="space-y-3">
            <Select
              id="eval-type"
              label="Alert type"
              value={evalType}
              onChange={(e) => setEvalType(e.target.value)}
              options={[
                { value: "system_log", label: "system_log" },
                { value: "network", label: "network" },
                { value: "authentication", label: "authentication" },
                { value: "endpoint", label: "endpoint" },
                { value: "email", label: "email" },
              ]}
            />
            <div>
              <label htmlFor="eval-message" className="block text-sm font-medium text-content-secondary mb-1.5">
                Message
              </label>
              <textarea
                id="eval-message"
                value={evalMessage}
                onChange={(e) => setEvalMessage(e.target.value)}
                rows={4}
                placeholder="e.g. Multiple failed password attempts for root from 203.0.113.10"
                className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary transition resize-none"
              />
            </div>
            <button
              type="submit"
              disabled={evaluating || !evalMessage.trim()}
              className="px-4 py-2 rounded-lg bg-accent-primary text-app-bg text-sm font-medium hover:opacity-90 transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {evaluating ? "Testing…" : "Test rules"}
            </button>
          </form>
          {evalResult && (
            <div className="mt-4 px-4 py-3 rounded-lg bg-status-success/10 border border-status-success/30 text-sm text-status-success">
              {evalResult}
            </div>
          )}
        </Card>

        <Card>
          <h2 className="text-lg font-semibold text-content-primary tracking-tight">Trigger on alert</h2>
          <p className="text-xs text-content-tertiary mt-0.5 mb-4">
            Fire the response playbook manually for an existing alert ID.
          </p>
          <form onSubmit={handleTrigger} className="space-y-3">
            <div>
              <label htmlFor="trigger-id" className="block text-sm font-medium text-content-secondary mb-1.5">
                Alert ID
              </label>
              <input
                id="trigger-id"
                type="number"
                min={1}
                value={triggerId}
                onChange={(e) => setTriggerId(e.target.value)}
                placeholder="e.g. 42"
                className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm font-mono text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary transition"
              />
            </div>
            <button
              type="submit"
              disabled={triggering || !triggerId}
              className="px-4 py-2 rounded-lg bg-accent-primary text-app-bg text-sm font-medium hover:opacity-90 transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {triggering ? "Triggering…" : "Execute actions"}
            </button>
          </form>
          {triggerResult && (
            <div className="mt-4 px-4 py-3 rounded-lg bg-status-success/10 border border-status-success/30 text-sm text-status-success">
              {triggerResult}
            </div>
          )}
        </Card>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      <Card padded={false} className="overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-line-subtle">
          <div>
            <h2 className="text-lg font-semibold text-content-primary tracking-tight">Executed actions</h2>
            <p className="text-xs text-content-tertiary mt-0.5">Automation audit trail for this organization.</p>
          </div>
          <button
            type="button"
            onClick={loadActions}
            className="px-4 py-2 rounded-lg bg-app-subtle hover:bg-line-bright border border-line-subtle text-sm text-content-primary transition"
          >
            Refresh
          </button>
        </div>
        {loading ? (
          <SkeletonTable rows={6} cols={5} />
        ) : actions.length === 0 ? (
          <EmptyState
            title="No automation actions recorded yet"
            description="Use the dry-run evaluator or trigger a playbook to see actions here."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
                  <th className="px-5 py-3.5">Action</th>
                  <th className="px-5 py-3.5 w-32">Severity</th>
                  <th className="px-5 py-3.5 w-28">Status</th>
                  <th className="px-5 py-3.5 w-24">Alert</th>
                  <th className="px-5 py-3.5 w-44">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-subtle text-sm">
                {actions.map((action) => (
                  <tr key={action.id} className="hover:bg-app-subtle/50 transition-colors">
                    <td className="px-5 py-3.5">
                      <span className="font-mono text-xs text-accent-primary">{action.action_type}</span>
                      {action.rule_name && (
                        <span className="block text-xs text-content-tertiary mt-0.5">{action.rule_name}</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border ${severityBadge[action.severity] || severityBadge.medium}`}>
                        {action.severity.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border ${statusBadge[action.status] || statusBadge.skipped}`}>
                        {action.status}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-xs text-content-tertiary">
                      {action.alert_id ? `#${action.alert_id}` : "-"}
                    </td>
                    <td className="px-5 py-3.5 text-xs text-content-tertiary whitespace-nowrap">
                      {action.created_at ? new Date(action.created_at).toLocaleString() : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && total > 0 && (
          <div className="flex flex-col sm:flex-row items-center justify-between px-5 py-3.5 border-t border-line-subtle text-xs text-content-secondary gap-3">
            <span>
              Showing <span className="text-content-primary font-medium">{(page - 1) * PAGE_SIZE + 1}</span> -{" "}
              <span className="text-content-primary font-medium">{Math.min(page * PAGE_SIZE, total)}</span> of{" "}
              <span className="text-content-primary font-medium">{total}</span> actions
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
        )}
      </Card>
    </div>
  );
};

export default SoarPage;