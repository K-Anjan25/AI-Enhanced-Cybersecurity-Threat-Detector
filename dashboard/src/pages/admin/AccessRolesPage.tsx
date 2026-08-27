import React, { useCallback, useEffect, useState } from "react";
import AdminApi from "../../api/adminApi";
import { PageHeader, SkeletonTable, EmptyState, Badge, Card, StatusBadge } from "../../components/ui";
import { ShieldCheck } from "lucide-react";
import { getApiError } from "../../utils/getApiError";

interface RoleRow {
  role: string;
  clearance: number;
  permissions: string[];
}

const ROLE_DESCRIPTIONS: Record<string, string> = {
  ADMIN: "Full platform access. Cross-tenant views, engine + user administration.",
  ANALYST: "Tier 1/2 analyst. Reads + writes alerts, analytics and detection rules.",
  USER: "Read-only observation of alerts and analytics within their tenant.",
};

const ROLE_ACCENT: Record<string, string> = {
  ADMIN: "bg-status-critical/15 text-status-critical border-status-critical/30",
  ANALYST: "bg-accent-primary/15 text-accent-primary border-accent-primary/30",
  USER: "bg-app-subtle text-content-secondary border-line-subtle",
};

const AccessRolesPage: React.FC = () => {
  const [rows, setRows] = useState<RoleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await AdminApi.fetchRolesMatrix();
      setRows(res.data);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load access roles"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const allPermissions = Array.from(new Set(rows.flatMap((r) => r.permissions))).sort();

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Access Roles"
        description="Attribute-based access control (ABAC) matrix. Permissions are granted by role and clamped by clearance level."
        backTo="/admin"
        crumbs={[{ label: "Admin", to: "/admin" }, { label: "Access Roles" }]}
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
        <SkeletonTable rows={3} cols={5} />
      ) : rows.length === 0 ? (
        <Card className="p-6">
          <EmptyState icon={<ShieldCheck size={28} />} title="No roles available" />
        </Card>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
              <tr>
                <th scope="col" className="px-5 py-3">Role</th>
                <th scope="col" className="px-5 py-3">Clearance</th>
                {allPermissions.map((perm) => (
                  <th key={perm} className="px-3 py-3 text-center">
                    {perm}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line-subtle text-sm">
              {rows.map((row) => (
                <tr key={row.role} className="hover:bg-app-subtle/50 transition">
                  <td className="px-5 py-3">
                    <div className="flex flex-col gap-1">
                      <Badge className={`${ROLE_ACCENT[row.role] || ROLE_ACCENT.USER} font-semibold capitalize w-fit`}>
                        {row.role.toLowerCase()}
                      </Badge>
                      <p className="text-xs text-content-tertiary max-w-xs">{ROLE_DESCRIPTIONS[row.role]}</p>
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <StatusBadge
                      tone={row.clearance >= 4 ? "critical" : row.clearance >= 2 ? "success" : "neutral"}
                      label={`L${row.clearance}`}
                    />
                  </td>
                  {allPermissions.map((perm) => {
                    const granted = row.permissions.includes(perm);
                    return (
                      <td key={perm} className="px-3 py-3 text-center" aria-label={`${row.role} ${perm}`}>
                        {granted ? (
                          <span className="inline-block w-2.5 h-2.5 rounded-full bg-status-success" title="Granted" />
                        ) : (
                          <span className="inline-block w-2.5 h-2.5 rounded-full bg-app-subtle border border-line-subtle" title="Not granted" />
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <p className="text-xs text-content-tertiary">
        Clearance-sensitive permissions (e.g. <code className="text-accent-primary">audit:read</code>,{" "}
        <code className="text-accent-primary">users:manage</code>) require rounding-up clearance even when the role
        grants them.
      </p>
    </div>
  );
};

export default AccessRolesPage;