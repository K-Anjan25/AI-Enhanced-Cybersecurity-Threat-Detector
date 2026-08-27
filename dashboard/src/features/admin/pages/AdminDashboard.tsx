import React from "react";
import { Link } from "react-router-dom";
import { useQuery } from "react-query";
import AdminApi from "../../../api/adminApi";
import RulesApi from "../../../api/rulesApi";
import { Term } from "../../../components/ui";

export interface DashboardMetric {
  title: string;
  value: string;
  status: string;
  color: string;
}

export default function AdminDashboard(): React.ReactElement {
  // Real platform metrics from the admin endpoints this role can already read.
  const { data: orgs } = useQuery(["adminOrgs"], AdminApi.fetchOrgs, {
    onError: () => undefined,
  });
  const { data: users = [] } = useQuery(
    ["adminUsers", ""],
    () => AdminApi.fetchRoster({}).catch(() => []),
    { onError: () => undefined }
  );
  const { data: rules } = useQuery(
    ["adminRules"],
    () => RulesApi.fetchRules(1, 1).catch(() => null),
    { onError: () => undefined }
  );

  const activeUsers = users.filter((u) => !u.is_blocked && u.is_active !== false).length;

  const metrics: DashboardMetric[] = [
    { title: "Provisioned Users", value: String(users.length), status: `${activeUsers} active`, color: "text-status-success" },
    { title: "Tenant Workspaces", value: String(orgs?.total ?? 0), status: orgs?.total ? "Isolated" : "Seeding", color: "text-accent-primary" },
    { title: "Detection Rules", value: String(rules?.total ?? 0), status: "Signature + heuristic", color: "text-status-warning" },
    { title: "AI Detection Engine", value: "v2.0.0", status: "Operational", color: "text-status-success" },
  ];

  const cardCls =
    "bg-app-surface hover:bg-line-bright/40 border border-line-subtle p-6 rounded-xl shadow-sm transition flex flex-col justify-between group";

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-content-primary tracking-wide">SOC System Administration</h1>
        <p className="text-content-secondary mt-1">
          Manage security analysts, AI detection models, and platform integrations.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {metrics.map((item, idx) => (
          <div key={idx} className="bg-app-surface border border-line-subtle rounded-xl p-5 shadow-sm">
            <span className="text-xs font-medium uppercase tracking-wider text-content-tertiary">
              {item.title}
            </span>
            <div className="flex items-baseline justify-between mt-3">
              <span className="text-2xl font-bold text-content-primary">{item.value}</span>
              <span className={`text-xs font-semibold ${item.color}`}>{item.status}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Link to="/admin/users" className={cardCls}>
          <div>
            <h3 className="text-lg font-semibold text-content-primary group-hover:text-accent-primary transition">
              User & Role Management
            </h3>
            <p className="text-sm text-content-secondary mt-2">
              Provision analyst accounts, assign security tiers (Admin, Analyst, Viewer), and enforce MFA.
            </p>
          </div>
          <span className="mt-6 text-accent-primary text-sm font-medium flex items-center">
            Manage Analysts &rarr;
          </span>
        </Link>

        <Link to="/admin/engine-settings" className={cardCls}>
          <div>
            <h3 className="text-lg font-semibold text-content-primary group-hover:text-accent-primary transition">
              AI & Detection Engine
            </h3>
            <p className="text-sm text-content-secondary mt-2">
              Configure anomaly <Term>confidence</Term> thresholds, <Term>detection</Term>{" "}
              sensitivity, and automated mitigation rules.
            </p>
          </div>
          <span className="mt-6 text-accent-primary text-sm font-medium flex items-center">
            Configure AI Engine &rarr;
          </span>
        </Link>

        <Link to="/admin/system-logs" className={cardCls}>
          <div>
            <h3 className="text-lg font-semibold text-content-primary group-hover:text-accent-primary transition">
              Audit Logs
            </h3>
            <p className="text-sm text-content-secondary mt-2">
              Review immutable audit trails of incident triage actions taken by security team members.
            </p>
          </div>
          <span className="mt-6 text-accent-primary text-sm font-medium flex items-center">
            View Audit Logs &rarr;
          </span>
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Link to="/admin/tenants" className={cardCls}>
          <div>
            <h3 className="text-lg font-semibold text-content-primary group-hover:text-accent-primary transition">
              Tenants
            </h3>
            <p className="text-sm text-content-secondary mt-2">
              Cross-tenant workspace overview: member counts and lifecycle for every organization.
            </p>
          </div>
          <span className="mt-6 text-accent-primary text-sm font-medium flex items-center">
            Browse Tenants &rarr;
          </span>
        </Link>

        <Link to="/admin/roles" className={cardCls}>
          <div>
            <h3 className="text-lg font-semibold text-content-primary group-hover:text-accent-primary transition">
              Access Roles
            </h3>
            <p className="text-sm text-content-secondary mt-2">
              Render the ABAC matrix: which permissions each role holds, clamped by clearance level.
            </p>
          </div>
          <span className="mt-6 text-accent-primary text-sm font-medium flex items-center">
            View Access Matrix &rarr;
          </span>
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Link to="/admin/rules" className={cardCls}>
          <div>
            <h3 className="text-lg font-semibold text-content-primary group-hover:text-accent-primary transition">
              Detection Rules
            </h3>
            <p className="text-sm text-content-secondary mt-2">
              Create, tune and toggle the signature/heuristic rules driving detections.
            </p>
          </div>
          <span className="mt-6 text-accent-primary text-sm font-medium flex items-center">
            Manage Rules &rarr;
          </span>
        </Link>

        <Link to="/admin/reputation" className={cardCls}>
          <div>
            <h3 className="text-lg font-semibold text-content-primary group-hover:text-accent-primary transition">
              IP Reputation
            </h3>
            <p className="text-sm text-content-secondary mt-2">
              Score and blacklist source IPs feeding threat-intel enrichment.
            </p>
          </div>
          <span className="mt-6 text-accent-primary text-sm font-medium flex items-center">
            Manage Reputation &rarr;
          </span>
        </Link>
      </div>
    </div>
  );
}
