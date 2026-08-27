import React, { useCallback, useEffect, useState } from "react";
import AuditApi, { AuditLogParams, AuditLogResponse } from "../../api/auditApi";
import { PageHeader, SkeletonTable, EmptyState } from "../../components/ui";
import { getApiError } from "../../utils/getApiError";

const PAGE_SIZE = 20;

interface AuditEntry {
  id: number;
  action: string;
  actor?: string | null;
  resource?: string | null;
  details?: string | null;
  ip_address?: string | null;
  created_at?: string | null;
}

const SystemLogs: React.FC = () => {
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionFilter, setActionFilter] = useState("");

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: AuditLogParams = { page, limit: PAGE_SIZE };
      if (actionFilter.trim()) params.action = actionFilter.trim();
      const response: AuditLogResponse = await AuditApi.getLogs(params);
      setLogs((response.data || []) as AuditEntry[]);
      setTotal(response.total || 0);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load audit logs"));
    } finally {
      setLoading(false);
    }
  }, [page, actionFilter]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="System Audit Logs"
        description="Immutable audit trail of administrative and detection-engine actions. Admin only."
        backTo="/admin"
        crumbs={[{ label: "Admin", to: "/admin" }, { label: "System Audit Logs" }]}
      />

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <input
          type="text"
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.target.value);
            setPage(1);
          }}
          placeholder="Filter by action (e.g. USER_BLOCKED)"
          className="w-full sm:w-80 bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary"
        />
        <button
          type="button"
          onClick={fetchLogs}
          className="px-4 py-2 rounded-lg bg-app-subtle hover:bg-line-bright border border-line-subtle text-sm text-content-primary transition"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      {loading ? (
        <SkeletonTable rows={8} cols={6} />
      ) : logs.length === 0 ? (
        <EmptyState
          icon="search"
          title="No audit entries found"
          description="Try clearing the action filter or checking back later."
        />
      ) : (
      <div className="bg-app-surface rounded-xl border border-line-subtle shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
              <tr>
                <th scope="col" className="px-5 py-3">Action</th>
                <th scope="col" className="px-5 py-3">Actor</th>
                <th scope="col" className="px-5 py-3">Resource</th>
                <th scope="col" className="px-5 py-3">Details</th>
                <th scope="col" className="px-5 py-3">Source IP</th>
                <th scope="col" className="px-5 py-3">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-subtle text-sm">
                {logs.map((log) => (
                  <tr key={log.id} className="hover:bg-app-subtle/50 transition">
                    <td className="px-5 py-3">
                      <span className="font-mono text-xs text-accent-primary bg-accent-primary/10 px-2 py-0.5 rounded">
                        {log.action}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-content-primary">{log.actor || "-"}</td>
                    <td className="px-5 py-3 text-content-secondary">{log.resource || "-"}</td>
                    <td className="px-5 py-3 text-content-secondary max-w-md truncate" title={log.details || ""}>
                      {log.details || "-"}
                    </td>
                    <td className="px-5 py-3 font-mono text-xs text-content-tertiary">{log.ip_address || "-"}</td>
                    <td className="px-5 py-3 text-xs text-content-tertiary whitespace-nowrap">
                      {log.created_at ? new Date(log.created_at).toLocaleString() : "-"}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-between px-5 py-3.5 border-t border-line-subtle text-xs text-content-secondary gap-3">
          <span>
            Showing <span className="text-content-primary font-medium">{total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1}</span>
            {" - "}
            <span className="text-content-primary font-medium">{Math.min(page * PAGE_SIZE, total)}</span> of{" "}
            <span className="text-content-primary font-medium">{total}</span> entries
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
      </div>
      )}
    </div>
  );
};

export default SystemLogs;
