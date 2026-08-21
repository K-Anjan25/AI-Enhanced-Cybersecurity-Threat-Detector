import React, { useCallback, useEffect, useState } from "react";
import SoarApi from "../api/soarApi";
import RulesApi from "../api/rulesApi";
import type { SoarAction, SoarPlaybook } from "../types/soar";
import {
  PageHeader,
  Card,
  Select,
  SkeletonTable,
  EmptyState,
} from "../components/ui";

const PAGE_SIZE = 10;

const statusBadge: Record<string, string> = {
  pending: "bg-status-warning/15 text-status-warning border-status-warning/30",
  executing: "bg-accent-primary/15 text-accent-primary border-accent-primary/30",
  executed: "bg-status-success/15 text-status-success border-status-success/30",
  failed: "bg-status-critical/15 text-status-critical border-status-critical/30",
  skipped: "bg-app-subtle text-content-secondary border-line-subtle",
};

const severityBadge: Record<string, string> = {
  low: "bg-status-success/15 text-status-success border-status-success/30",
  medium: "bg-chart-4/15 text-chart-4 border-chart-4/30",
  high: "bg-status-warning/15 text-status-warning border-status-warning/30",
  critical: "bg-status-critical/15 text-status-critical border-status-critical/30",
};

const PLAYBOOK_ACTIONS = [
  "BLOCK_SOURCE_IP",
  "QUARANTINE_ENDPOINT",
  "REVOKE_CREDENTIALS",
  "ALERT_OPERATOR",
  "DISABLE_ACCOUNT",
  "REVIEW_ONLY",
];

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

  const [playbooks, setPlaybooks] = useState<SoarPlaybook[]>([]);
  const [rules, setRules] = useState<Array<{ id: number; name: string }>>([]);
  const [pbRuleId, setPbRuleId] = useState<string>("");
  const [pbName, setPbName] = useState<string>("");
  const [pbAction, setPbAction] = useState<string>("BLOCK_SOURCE_IP");
  const [pbLoading, setPbLoading] = useState(true);
  const [pbSaving, setPbSaving] = useState(false);
  const [pbError, setPbError] = useState<string | null>(null);

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

  const loadPlaybooks = useCallback(async () => {
    setPbError(null);
    try {
      const [pbRes, ruleRes] = await Promise.all([
        SoarApi.fetchPlaybooks({ page: 1, limit: 200 }),
        RulesApi.fetchRules(1, 100),
      ]);
      setPlaybooks(pbRes.data);
      const used = new Set(pbRes.data.map((pb) => pb.rule_id));
      setRules(ruleRes.data.filter((r) => !used.has(r.id)));
    } catch (err: any) {
      setPbError(err?.detail || "Failed to load playbooks");
    } finally {
      setPbLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPlaybooks();
  }, [loadPlaybooks]);

  const handleCreatePlaybook = async (e: React.FormEvent) => {
    e.preventDefault();
    const ruleId = Number(pbRuleId);
    if (!Number.isInteger(ruleId) || ruleId <= 0 || !pbName.trim()) return;
    setPbSaving(true);
    setPbError(null);
    try {
      await SoarApi.createPlaybook({
        rule_id: ruleId,
        name: pbName.trim(),
        action_type: pbAction,
      });
      setPbRuleId("");
      setPbName("");
      setPbAction("BLOCK_SOURCE_IP");
      await loadPlaybooks();
    } catch (err: any) {
      setPbError(err?.detail || "Failed to create playbook");
    } finally {
      setPbSaving(false);
    }
  };

  const handleTogglePlaybook = async (pb: SoarPlaybook) => {
    try {
      await SoarApi.updatePlaybook(pb.id, { is_active: !pb.is_active });
      await loadPlaybooks();
    } catch (err: any) {
      setPbError(err?.detail || "Failed to update playbook");
    }
  };

  const handleDeletePlaybook = async (pb: SoarPlaybook) => {
    try {
      await SoarApi.deletePlaybook(pb.id);
      await loadPlaybooks();
    } catch (err: any) {
      setPbError(err?.detail || "Failed to delete playbook");
    }
  };

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

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-content-primary tracking-tight">Playbooks</h2>
            <p className="text-xs text-content-tertiary mt-0.5">
              Pin a detection rule to a specific action, overriding the default mapping.
            </p>
          </div>
        </div>

        <form onSubmit={handleCreatePlaybook} className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
          <Select
            id="pb-rule"
            label="Rule"
            value={pbRuleId}
            onChange={(e) => setPbRuleId(e.target.value)}
            options={rules.map((r) => ({ value: String(r.id), label: r.name }))}
          />
          <div>
            <label htmlFor="pb-name" className="block text-sm font-medium text-content-secondary mb-1.5">
              Name
            </label>
            <input
              id="pb-name"
              value={pbName}
              onChange={(e) => setPbName(e.target.value)}
              placeholder="e.g. Escalate brute force"
              className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary transition"
            />
          </div>
          <div>
            <Select
              id="pb-action"
              label="Action"
              value={pbAction}
              onChange={(e) => setPbAction(e.target.value)}
              options={PLAYBOOK_ACTIONS.map((a) => ({ value: a, label: a }))}
            />
            <button
              type="submit"
              disabled={pbSaving || !pbRuleId || !pbName.trim()}
              className="mt-1.5 w-full px-4 py-2 rounded-lg bg-accent-primary text-app-bg text-sm font-medium hover:opacity-90 transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {pbSaving ? "Saving…" : "Add playbook"}
            </button>
          </div>
        </form>

        {pbError && (
          <div className="mt-3 px-4 py-2.5 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
            {pbError}
          </div>
        )}

        {pbLoading ? (
          <div className="mt-4">
            <SkeletonTable rows={3} cols={4} />
          </div>
        ) : playbooks.length === 0 ? (
          <EmptyState
            title="No playbooks yet"
            description="Add a playbook to override a rule's default response action."
          />
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Rule</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3 w-24">State</th>
                  <th className="px-4 py-3 w-28">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-subtle text-sm">
                {playbooks.map((pb) => (
                  <tr key={pb.id} className="hover:bg-app-subtle/50 transition-colors">
                    <td className="px-4 py-3 text-content-primary">{pb.name}</td>
                    <td className="px-4 py-3 text-xs text-content-tertiary">{pb.rule_name || "—"}</td>
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs text-accent-primary">{pb.action_type}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border ${pb.is_active ? "bg-status-success/15 text-status-success border-status-success/30" : "bg-app-subtle text-content-secondary border-line-subtle"}`}>
                        {pb.is_active ? "active" : "paused"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleTogglePlaybook(pb)}
                          className="px-2.5 py-1 bg-app-subtle hover:bg-line-bright border border-line-subtle text-xs text-content-secondary rounded-lg transition"
                        >
                          {pb.is_active ? "Pause" : "Enable"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeletePlaybook(pb)}
                          className="px-2.5 py-1 bg-status-critical/10 hover:bg-status-critical/20 border border-status-critical/30 text-xs text-status-critical rounded-lg transition"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

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