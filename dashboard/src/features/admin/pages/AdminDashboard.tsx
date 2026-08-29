import React from "react";
import { Link } from "react-router-dom";
import { useQuery } from "react-query";
import { KeyRound, Building2, ListChecks, Cpu, ArrowRight } from "lucide-react";
import AdminApi from "../../../api/adminApi";
import RulesApi from "../../../api/rulesApi";
import { Card, PageHeader, StatCard, Term } from "../../../components/ui";

export interface DashboardMetric {
  title: string;
  value: string;
  status: string;
  tone: "default" | "success" | "warning" | "critical" | "accent";
}

interface AdminLink {
  to: string;
  title: string;
  body: React.ReactNode;
  cta: string;
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
    {
      title: "Provisioned Users",
      value: String(users.length),
      status: `${activeUsers} active`,
      tone: "success",
    },
    {
      title: "Tenant Workspaces",
      value: String(orgs?.total ?? 0),
      status: orgs?.total ? "Isolated" : "Seeding",
      tone: "accent",
    },
    {
      title: "Detection Rules",
      value: String(rules?.total ?? 0),
      status: "Signature + heuristic",
      tone: "warning",
    },
    {
      title: "AI Detection Engine",
      value: "v2.0.0",
      status: "Operational",
      tone: "success",
    },
  ];

  const metricIcons = [KeyRound, Building2, ListChecks, Cpu];

  const primaryLinks: AdminLink[] = [
    {
      to: "/admin/users",
      title: "User & Role Management",
      body: "Provision analyst accounts, assign security tiers (Admin, Analyst, Viewer), and enforce MFA.",
      cta: "Manage Analysts",
    },
    {
      to: "/admin/engine-settings",
      title: "AI & Detection Engine",
      body: (
        <>
          Configure anomaly <Term>confidence</Term> thresholds, <Term>detection</Term>{" "}
          sensitivity, and automated mitigation rules.
        </>
      ),
      cta: "Configure AI Engine",
    },
    {
      to: "/admin/system-logs",
      title: "Audit Logs",
      body: "Review immutable audit trails of incident triage actions taken by security team members.",
      cta: "View Audit Logs",
    },
  ];

  const secondaryLinks: AdminLink[] = [
    {
      to: "/admin/tenants",
      title: "Tenants",
      body: "Cross-tenant workspace overview: member counts and lifecycle for every organization.",
      cta: "Browse Tenants",
    },
    {
      to: "/admin/roles",
      title: "Access Roles",
      body: "Render the ABAC matrix: which permissions each role holds, clamped by clearance level.",
      cta: "View Access Matrix",
    },
    {
      to: "/admin/rules",
      title: "Detection Rules",
      body: "Create, tune and toggle the signature/heuristic rules driving detections.",
      cta: "Manage Rules",
    },
    {
      to: "/admin/reputation",
      title: "IP Reputation",
      body: "Score and blacklist source IPs feeding threat-intel enrichment.",
      cta: "Manage Reputation",
    },
    {
      to: "/admin/sso",
      title: "SSO & SCIM",
      body: "Configure OIDC single sign-on and SCIM provisioning for enterprise identity providers.",
      cta: "Manage SSO/SCIM",
    },
  ];

  const renderLinkCard = (link: AdminLink): React.ReactElement => (
    <Card key={link.to} padded={false} interactive={false} className="p-6">
      <Link to={link.to} className="group flex flex-col justify-between h-full">
        <div>
          <h3 className="text-base font-semibold text-content-primary group-hover:text-accent-primary transition tracking-tight">
            {link.title}
          </h3>
          <p className="text-sm text-content-secondary mt-2 leading-relaxed">{link.body}</p>
        </div>
        <span className="mt-6 text-accent-primary text-sm font-semibold flex items-center gap-1.5">
          {link.cta}
          <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" aria-hidden />
        </span>
      </Link>
    </Card>
  );

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Administration"
        description="Manage security analysts, AI detection models, and platform integrations."
      />

      {/* Platform metrics — the shared StatCard pattern (tone + tabular numbers). */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map((item, idx) => {
          const Icon = metricIcons[idx];
          return (
            <StatCard
              key={item.title}
              label={item.title}
              value={item.value}
              hint={item.status}
              tone={item.tone}
              icon={<Icon size={16} aria-hidden />}
            />
          );
        })}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">{primaryLinks.map(renderLinkCard)}</div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {secondaryLinks.map(renderLinkCard)}
      </div>
    </div>
  );
}
