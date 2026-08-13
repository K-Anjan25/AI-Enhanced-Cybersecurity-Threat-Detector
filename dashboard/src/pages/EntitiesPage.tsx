import React, { useCallback, useEffect, useState } from "react";
import EntityApi from "../api/entityApi";
import EntityGraphView from "../features/entities/components/EntityGraphView";
import type { EntityType, ThreatEntity } from "../types/entity";

const PAGE_SIZE = 12;
const ENTITY_TYPES: Array<{ value: EntityType | ""; label: string }> = [
  { value: "", label: "All types" },
  { value: "ip", label: "IP address" },
  { value: "domain", label: "Domain" },
  { value: "hash", label: "File hash" },
  { value: "email", label: "Email" },
  { value: "file", label: "File" },
];

const typeColor: Record<string, string> = {
  ip: "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
  domain: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  hash: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  email: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  file: "bg-red-500/15 text-red-400 border-red-500/30",
};

const riskColor = (score: number): string => {
  if (score >= 75) return "bg-red-500/15 text-red-400 border-red-500/30";
  if (score >= 50) return "bg-orange-500/15 text-orange-400 border-orange-500/30";
  if (score >= 25) return "bg-amber-500/15 text-amber-300 border-amber-500/30";
  return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
};

const EntitiesPage: React.FC = () => {
  const [entities, setEntities] = useState<ThreatEntity[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [typeFilter, setTypeFilter] = useState<EntityType | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [graphRoot, setGraphRoot] = useState<ThreatEntity | null>(null);
  const [adjustingId, setAdjustingId] = useState<number | null>(null);

  const loadEntities = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: { page: number; limit: number; entity_type?: EntityType } = {
        page,
        limit: PAGE_SIZE,
      };
      if (typeFilter) params.entity_type = typeFilter;
      const response = await EntityApi.fetchEntities(params);
      setEntities(response.data);
      setTotal(response.total);
    } catch (err: any) {
      setError(err?.detail || "Failed to load entities");
    } finally {
      setLoading(false);
    }
  }, [page, typeFilter]);

  useEffect(() => {
    loadEntities();
  }, [loadEntities]);

  const handleRiskAdjust = async (entity: ThreatEntity, riskScore: number) => {
    setAdjustingId(entity.id);
    try {
      const updated = await EntityApi.updateEntityRisk(entity.id, riskScore);
      setEntities((prev) => prev.map((e) => (e.id === entity.id ? updated : e)));
    } catch (err: any) {
      setError(err?.detail || "Failed to update reputation");
    } finally {
      setAdjustingId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-content-primary">Entity graph</h1>
        <p className="text-sm text-content-secondary mt-1">
          Extracted indicators from detected threats. Click "Graph" to explore connections.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <select
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value as EntityType | "");
            setPage(1);
          }}
          className="px-3 py-2 bg-app-bg border border-line-subtle rounded-lg text-sm text-content-primary focus:outline-none focus:border-accent-primary transition cursor-pointer"
          aria-label="Filter by entity type"
        >
          {ENTITY_TYPES.map((type) => (
            <option key={type.value || "all"} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={loadEntities}
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
                <th className="px-5 py-3.5 w-28">Type</th>
                <th className="px-5 py-3.5">Indicator</th>
                <th className="px-5 py-3.5 w-32">Risk score</th>
                <th className="px-5 py-3.5 w-24">Occurrences</th>
                <th className="px-5 py-3.5 w-28">Last seen</th>
                <th className="px-5 py-3.5 w-40 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-subtle text-sm">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-content-tertiary">
                    Loading entities...
                  </td>
                </tr>
              ) : entities.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-content-tertiary">
                    No entities{typeFilter ? ` of type "${typeFilter}"` : ""} found.
                  </td>
                </tr>
              ) : (
                entities.map((entity) => (
                  <tr key={entity.id} className="hover:bg-app-subtle/50 transition-colors">
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border ${typeColor[entity.entity_type] || typeColor.ip}`}>
                        {entity.entity_type.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 font-mono text-xs text-accent-primary max-w-md truncate" title={entity.value}>
                      {entity.value}
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 bg-app-subtle rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${Math.min(entity.risk_score, 100)}%`,
                              backgroundColor:
                                entity.risk_score >= 75
                                  ? "#f87171"
                                  : entity.risk_score >= 50
                                  ? "#fb923c"
                                  : entity.risk_score >= 25
                                  ? "#fbbf24"
                                  : "#34d399",
                            }}
                          />
                        </div>
                        <span className={`px-2 py-0.5 rounded-md text-xs font-medium border ${riskColor(entity.risk_score)}`}>
                          {entity.risk_score.toFixed(1)}
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-content-secondary">{entity.occurrences}</td>
                    <td className="px-5 py-3.5 text-xs text-content-tertiary whitespace-nowrap">
                      {entity.last_seen ? new Date(entity.last_seen).toLocaleString() : "-"}
                    </td>
                    <td className="px-5 py-3.5 text-right whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => setGraphRoot(entity)}
                        className="px-3 py-1.5 mr-2 rounded-lg bg-accent-primary/10 hover:bg-accent-primary/20 border border-accent-primary/30 text-xs font-medium text-accent-primary transition disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        Graph
                      </button>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        step={5}
                        defaultValue={entity.risk_score}
                        onChange={(e) => {
                          const value = Number(e.target.value);
                          if (!Number.isNaN(value) && value >= 0 && value <= 100) {
                            handleRiskAdjust(entity, value);
                          }
                        }}
                        disabled={adjustingId === entity.id}
                        className="w-16 px-2 py-1.5 bg-app-bg border border-line-subtle rounded-lg text-xs font-mono text-content-primary focus:outline-none focus:border-accent-primary transition disabled:opacity-40"
                        aria-label={`Override risk score for ${entity.value}`}
                        title="Set risk score (0-100)"
                      />
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
              <span className="text-content-primary font-medium">{total}</span> entities
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

      {graphRoot && (
        <EntityGraphView
          root={graphRoot}
          onPivot={(entity) => setGraphRoot(entity)}
          onClose={() => setGraphRoot(null)}
        />
      )}
    </div>
  );
};

export default EntitiesPage;