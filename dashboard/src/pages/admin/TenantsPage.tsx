import React, { useCallback, useEffect, useState } from "react";
import AdminApi, { OrgInfo } from "../../api/adminApi";
import { PageHeader, SkeletonTable, EmptyState, StatusBadge, Card } from "../../components/ui";
import { Users, Building2 } from "lucide-react";
import { getApiError } from "../../utils/getApiError";

const TenantsPage: React.FC = () => {
  const [orgs, setOrgs] = useState<OrgInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await AdminApi.fetchOrgs();
      setOrgs(res.data);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load tenants"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const totalUsers = orgs.reduce((sum, o) => sum + (o.user_count || 0), 0);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Tenants"
        description="Cross-tenant workspace overview for SOC administrators. Every tenant is isolated from the others."
        backTo="/admin"
        crumbs={[{ label: "Admin", to: "/admin" }, { label: "Tenants" }]}
        actions={
          <button
            type="button"
            onClick={load}
            className="px-4 py-2 rounded-lg bg-app-subtle hover:bg-line-bright border border-line-subtle text-sm text-content-primary transition"
          >
            Refresh
          </button>
        }
      />

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      {loading ? (
        <SkeletonTable rows={5} cols={4} />
      ) : orgs.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={<Building2 size={28} />}
            title="No tenants found"
            description="Provision an organization to begin onboarding teams."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {orgs.map((org) => (
            <Card key={org.id} className="p-5 flex flex-col gap-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="w-9 h-9 rounded-lg bg-accent-primary/15 text-accent-primary flex items-center justify-center shrink-0">
                    <Building2 size={18} aria-hidden />
                  </span>
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-content-primary truncate">{org.name}</h3>
                    <p className="text-xs font-mono text-content-tertiary truncate">{org.slug}</p>
                  </div>
                </div>
                <StatusBadge tone="success" label="Active" />
              </div>

              {org.description && (
                <p className="text-xs text-content-secondary line-clamp-2">{org.description}</p>
              )}

              <div className="pt-3 border-t border-line-subtle flex items-center justify-between">
                <span className="text-xs text-content-secondary flex items-center gap-1.5">
                  <Users size={14} aria-hidden /> Members
                </span>
                <span className="text-lg font-bold text-content-primary tabular-nums">{org.user_count}</span>
              </div>

              <p className="text-[11px] text-content-tertiary">
                Created {org.created_at ? new Date(org.created_at).toLocaleDateString() : "—"}
              </p>
            </Card>
          ))}
        </div>
      )}

      {!loading && orgs.length > 0 && (
        <p className="text-xs text-content-tertiary">
          {orgs.length} tenant{orgs.length === 1 ? "" : "s"} · {totalUsers} member{totalUsers === 1 ? "" : "s"} across
          all workspaces
        </p>
      )}
    </div>
  );
};

export default TenantsPage;