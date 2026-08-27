import React, { useCallback, useEffect, useState } from "react";
import Button from "../components/ui/Button";
import IncidentApi from "../api/incidentApi";
import CreateIncidentModal from "../features/incidents/components/CreateIncidentModal";
import {
  PageHeader,
  Card,
  Select,
  SkeletonTable,
  EmptyState,
} from "../components/ui";
import type {
  CreateIncidentPayload,
  Incident,
  UpdateIncidentPayload,
} from "../types/incident";
import type { PaginatedResponse } from "../types/pagination";
import { getApiError } from "../utils/getApiError";

const PAGE_SIZE = 10;
const STATUSES = ["open", "triaging", "resolved", "closed"] as const;
const PRIORITIES = ["low", "medium", "high", "critical"] as const;

const priorityBadge: Record<string, string> = {
  low: "bg-status-success/15 text-status-success border-status-success/30",
  medium: "bg-chart-4/15 text-chart-4 border-chart-4/30",
  high: "bg-status-warning/15 text-status-warning border-status-warning/30",
  critical: "bg-status-critical/15 text-status-critical border-status-critical/30",
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
      setError(getApiError(err, "Failed to load incidents"));
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
      setError(getApiError(err, "Failed to update incident"));
    } finally {
      setUpdatingId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Incidents"
        description="Track and triage security incidents from detection to closure."
        actions={
          <Button variant="primary" onClick={() => setShowCreate(true)}>
            + New incident
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="w-52">
          <Select
            id="incident-status-filter"
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            options={[
              { value: "", label: "All statuses" },
              ...STATUSES.map((s) => ({ value: s, label: s.charAt(0).toUpperCase() + s.slice(1) })),
            ]}
          />
        </div>
        <Button type="button" variant="secondary" onClick={loadIncidents}>
          Refresh
        </Button>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      <Card padded={false} className="overflow-hidden">
        {loading ? (
          <SkeletonTable rows={6} cols={5} />
        ) : incidents.length === 0 ? (
          <EmptyState
            title={`No incidents${statusFilter ? ` with status "${statusFilter}"` : ""} found`}
            description="Create a new incident to begin tracking an investigation."
          />
        ) : (
          <>
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
                  {incidents.map((incident) => {
                    return (
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
                            <span className="text-xs text-content-tertiary">Saving…</span>
                          ) : (
                            <select
                              value={incident.status}
                              onChange={(e) =>
                                handleUpdate(incident, { status: e.target.value as Incident["status"] })
                              }
                              className="px-2.5 py-1.5 rounded-md text-xs font-medium border bg-app-bg cursor-pointer focus:outline-none focus:border-accent-primary transition"
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
                    );
                  })}
                </tbody>
              </table>
            </div>

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
          </>
        )}
      </Card>

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