import React, { useCallback, useEffect, useState } from "react";
import Button from "../components/ui/Button";
import IncidentApi from "../api/incidentApi";
import CreateIncidentModal from "../features/incidents/components/CreateIncidentModal";
import type {
  CreateIncidentPayload,
  Incident,
  UpdateIncidentPayload,
} from "../types/incident";
import type { PaginatedResponse } from "../types/pagination";

const PAGE_SIZE = 10;
const STATUSES = ["open", "triaging", "resolved", "closed"] as const;
const PRIORITIES = ["low", "medium", "high", "critical"] as const;

const statusBadge: Record<string, string> = {
  open: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  triaging: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  resolved: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  closed: "bg-app-subtle text-content-secondary border-line-subtle",
};

const priorityBadge: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  medium: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  high: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  critical: "bg-red-500/15 text-red-400 border-red-500/30",
};

const IncidentsPage: React.FC = () => {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  const loadIncidents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: { page: number; limit: number; status?: string } = {
        page,
        limit: PAGE_SIZE,
      };
      if (statusFilter) params.status = statusFilter;
      const response: PaginatedResponse<Incident> = await IncidentApi.fetchIncidents(params);
      setIncidents(response.data);
      setTotal(response.total);
    } catch (err: any) {
      setError(err?.detail || "Failed to load incidents");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    loadIncidents();
  }, [loadIncidents]);

  const handleCreate = async (payload: CreateIncidentPayload) => {
    setCreating(true);
    try {
      await IncidentApi.createIncident(payload);
      setShowCreate(false);
      setPage(1);
      await loadIncidents();
    } finally {
      setCreating(false);
    }
  };

  const handleUpdate = async (incident: Incident, changes: UpdateIncidentPayload) => {
    setUpdatingId(incident.id);
    try {
      await IncidentApi.updateIncident(incident.id, changes);
      await loadIncidents();
    } catch (err: any) {
      setError(err?.detail || "Failed to update incident");
    } finally {
      setUpdatingId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">Incidents</h1>
          <p className="text-sm text-content-secondary mt-1">
            Track and triage security incidents from detection to closure.
          </p>
        </div>
        <Button variant="primary" onClick={() => setShowCreate(true)}>
          + New incident
        </Button>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2 bg-app-bg border border-line-subtle rounded-lg text-sm text-content-primary focus:outline-none focus:border-accent-primary transition cursor-pointer"
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          {STATUSES.map((status) => (
            <option key={status} value={status}>
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={loadIncidents}
          className="px-4 py-2 rounded-lg bg-app-subtle hover:bg-line-bright border border-line-subtle text-sm text-content-primary transition"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-400">
          {error}
        </div>
      )}

      <div className="bg-app-surface rounded-xl border border-line-subtle shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
                <th className="px-5 py-3.5">Title</th>
                <th className="px-5 py-3.5 w-40">Status</th>
                <th className="px-5 py-3.5 w-32">Priority</th>
                <th className="px-5 py-3.5 w-36">Source alert</th>
                <th className="px-5 py-3.5 w-44">Last updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-subtle text-sm">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-content-tertiary">
                    Loading incidents...
                  </td>
                </tr>
              ) : incidents.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-content-tertiary">
                    No incidents{statusFilter ? ` with status "${statusFilter}"` : ""} found.
                  </td>
                </tr>
              ) : (
                incidents.map((incident) => (
                  <tr key={incident.id} className="hover:bg-app-subtle/50 transition-colors">
                    <td className="px-5 py-3.5 max-w-md">
                      <p className="text-content-primary font-medium truncate" title={incident.title}>
                        {incident.title}
                      </p>
                      {incident.description && (
                        <p className="text-xs text-content-tertiary truncate mt-0.5" title={incident.description}>
                          {incident.description}
                        </p>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      {updatingId === incident.id ? (
                        <span className="text-xs text-content-tertiary">Saving...</span>
                      ) : (
                        <select
                          value={incident.status}
                          onChange={(e) =>
                            handleUpdate(incident, { status: e.target.value as Incident["status"] })
                          }
                          className={`px-2.5 py-1.5 rounded-md text-xs font-medium border bg-app-bg cursor-pointer focus:outline-none focus:border-accent-primary transition ${statusBadge[incident.status] || statusBadge.open}`}
                          aria-label={`Status for ${incident.title}`}
                        >
                          {STATUSES.map((status) => (
                            <option key={status} value={status}>
                              {status.charAt(0).toUpperCase() + status.slice(1)}
                            </option>
                          ))}
                        </select>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <select
                        value={incident.priority}
                        onChange={(e) =>
                          handleUpdate(incident, { priority: e.target.value as Incident["priority"] })
                        }
                        className={`px-2.5 py-1.5 rounded-md text-xs font-medium border bg-app-bg cursor-pointer focus:outline-none focus:border-accent-primary transition ${priorityBadge[incident.priority] || priorityBadge.medium}`}
                        aria-label={`Priority for ${incident.title}`}
                      >
                        {PRIORITIES.map((priority) => (
                          <option key={priority} value={priority}>
                            {priority.charAt(0).toUpperCase() + priority.slice(1)}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-5 py-3.5 text-xs text-content-tertiary whitespace-nowrap">
                      {incident.source_alert_id ? `#${incident.source_alert_id}` : "-"}
                    </td>
                    <td className="px-5 py-3.5 text-xs text-content-tertiary whitespace-nowrap">
                      {incident.updated_at ? new Date(incident.updated_at).toLocaleString() : "-"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {!loading && total > 0 && (
          <div className="flex flex-col sm:flex-row items-center justify-between px-5 py-3.5 border-t border-line-subtle text-xs text-content-secondary gap-3">
            <span>
              Showing <span className="text-content-primary font-medium">{(page - 1) * PAGE_SIZE + 1}</span> -{" "}
              <span className="text-content-primary font-medium">{Math.min(page * PAGE_SIZE, total)}</span> of{" "}
              <span className="text-content-primary font-medium">{total}</span> incidents
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
      </div>

      {showCreate && (
        <CreateIncidentModal
          onClose={() => setShowCreate(false)}
          onSubmit={handleCreate}
          submitting={creating}
        />
      )}
    </div>
  );
};

export default IncidentsPage;