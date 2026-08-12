import React from "react";
import { Link } from "react-router-dom";

export interface DashboardMetric {
  title: string;
  value: string;
  status: string;
  color: string;
}

export default function AdminDashboard(): React.ReactElement {
  const metrics: DashboardMetric[] = [
    { title: "Active SOC Analysts", value: "12", status: "Online", color: "text-status-success" },
    { title: "AI Detection Engine", value: "v2.0.0", status: "Operational", color: "text-status-success" },
    { title: "Ingested Logs / Min", value: "14,250", status: "Normal Load", color: "text-accent-primary" },
    { title: "Active System Rules", value: "84", status: "4 Updated Today", color: "text-status-warning" },
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
              Configure anomaly confidence thresholds, detection sensitivity, and automated mitigation rules.
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
    </div>
  );
}
