import React, { Suspense, JSX } from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { useSelector } from "react-redux";
import type { RootState } from "./store/store";

import DashboardLayout from "./layouts/DashboardLayout";
import RequireAuth from "./routes/RequireAuth";
import Login from "./features/auth/pages/Login";
import Register from "./features/auth/pages/Register";
import Profile from "./features/account/pages/Profile";
import Account from "./features/account/components/Account";
import ResetPassword from "./features/auth/components/ResetPassword";

const ThreatAlertsPage = React.lazy(() => import("./features/alerts/pages/ThreatAlertsPage"));
const LogHistoryPage = React.lazy(() => import("./features/system/pages/LogHistoryPage"));
const AIAnalyticsPage = React.lazy(() => import("./features/analytics/pages/AIAnalyticsPage"));
const IncidentsPage = React.lazy(() => import("./features/incidents/pages/IncidentsPage"));
const EntitiesPage = React.lazy(() => import("./features/entities/pages/EntitiesPage"));
const SoarPage = React.lazy(() => import("./features/soar/pages/SoarPage"));
const DashboardOverviewPage = React.lazy(() => import("./features/dashboard/pages/DashboardOverviewPage"));
const BriefPage = React.lazy(() => import("./features/inbox/pages/BriefPage"));
const FeedPage = React.lazy(() => import("./features/cases/pages/FeedPage"));
const CasePage = React.lazy(() => import("./features/cases/pages/CasePage"));
const ActionsPage = React.lazy(() => import("./features/actions/pages/ActionsPage"));
const ReportsPage = React.lazy(() => import("./features/reports/pages/ReportsPage"));
const AdminDashboard = React.lazy(() => import("./features/admin/pages/AdminDashboard"));
const AdminUsers = React.lazy(() => import("./features/admin/pages/AdminUsers"));
const AdminEngineSettings = React.lazy(() => import("./features/admin/pages/EngineSettingsPage"));
const AdminAuditLogs = React.lazy(() => import("./features/admin/pages/SystemLogsPage"));
const TenantsPage = React.lazy(() => import("./features/admin/pages/TenantsPage"));
const AccessRolesPage = React.lazy(() => import("./features/admin/pages/AccessRolesPage"));
const RulesPage = React.lazy(() => import("./features/admin/pages/RulesPage"));
const ReputationPage = React.lazy(() => import("./features/admin/pages/ReputationPage"));
const SsoScimPage = React.lazy(() => import("./features/admin/pages/SsoScimPage"));
const ApiKeysPage = React.lazy(() => import("./features/admin/pages/ApiKeysPage"));
const CompliancePage = React.lazy(() => import("./features/admin/pages/CompliancePage"));
const LandingPage = React.lazy(() => import("./features/landing/pages/LandingPage"));
const SOCWallPage = React.lazy(() => import("./features/advanced/pages/SOCWallPage"));
const AttackCoveragePage = React.lazy(() => import("./features/coverage/pages/AttackCoveragePage"));
const ResponseTimesPage = React.lazy(() => import("./features/analytics/pages/ResponseTimesPage"));
const GdprRequestsPage = React.lazy(() => import("./features/retention/pages/GdprRequestsPage"));
const AssetInventoryPage = React.lazy(() => import("./features/assets/pages/AssetInventoryPage"));
const DataRetentionPage = React.lazy(() => import("./features/retention/pages/DataRetentionPage"));
const Final10Page = React.lazy(() => import("./features/advanced/pages/Final10Page"));
const ModulePage = React.lazy(() => import("./features/modules/pages/ModulePage"));
const AgentChatPage = React.lazy(() => import("./features/modules/pages/AgentChatPage"));

const FallbackLoader: React.FC = () => (
  <div className="flex justify-center items-center h-screen bg-app-bg text-content-secondary font-mono text-sm">
    <div className="flex items-center space-x-2">
      <div className="w-3 h-3 bg-accent-primary rounded-full animate-ping" />
      <span>Loading NOCTRA...</span>
    </div>
  </div>
);

export default function App(): JSX.Element {
  const { user, loading } = useSelector((state: RootState) => state.user);

  if (loading) {
    return <FallbackLoader />;
  }

  const storedRole = localStorage.getItem("user_role")?.toUpperCase();
  const userRoles: string[] = (
    (user as any)?.roles ||
    (storedRole ? [storedRole] : localStorage.getItem("auth_status") ? ["ANALYST"] : [])
  ).map((role: string) => role.toUpperCase());

  const storedPermissions = localStorage.getItem("user_permissions");
  const parsedStoredPermissions: string[] = (() => {
    try {
      return storedPermissions ? JSON.parse(storedPermissions) : [];
    } catch {
      return [];
    }
  })();
  const userPermissions: string[] = (user as any)?.permissions?.length
    ? (user as any).permissions
    : parsedStoredPermissions;

  return (
    <Router>
      <Suspense fallback={<FallbackLoader />}>
        <Routes>
          <Route path="/welcome" element={<LandingPage />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/reset-password" element={<ResetPassword />} />

          <Route
            path="/"
            element={
              <RequireAuth
                allowedRoles={["ANALYST", "USER", "ADMIN"]}
                roles={userRoles}
                permissions={userPermissions}
              />
            }
          >
            <Route element={<DashboardLayout />}>
              <Route index element={<BriefPage />} />
              <Route path="feed" element={<FeedPage />} />
              <Route path="case/:id" element={<CasePage />} />
              <Route path="actions" element={<ActionsPage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route path="dashboard" element={<DashboardOverviewPage />} />
              <Route path="alerts" element={<ThreatAlertsPage />} />
              <Route path="logs" element={<LogHistoryPage />} />
              <Route path="analytics" element={<AIAnalyticsPage />} />
              <Route path="incidents" element={<IncidentsPage />} />
              <Route path="entities" element={<EntitiesPage />} />
              <Route path="soar" element={<SoarPage />} />
              <Route path="soc-tv-wall" element={<SOCWallPage />} />
              <Route path="attack-coverage" element={<AttackCoveragePage />} />
              <Route path="response-times" element={<ResponseTimesPage />} />
              <Route path="erasure-requests" element={<GdprRequestsPage />} />
              <Route path="assets" element={<AssetInventoryPage />} />
              <Route path="retention" element={<DataRetentionPage />} />
              <Route path="final10" element={<Final10Page />} />
              <Route path="attack-path" element={<Final10Page />} />
              <Route path="drp" element={<Final10Page />} />
              <Route path="posture-score" element={<Final10Page />} />
              <Route path="noctra-os" element={<Final10Page />} />
              <Route path="ztna" element={<ModulePage />} />
              <Route path="hunting" element={<ModulePage />} />
              <Route path="vulns" element={<ModulePage />} />
              <Route path="cspm" element={<ModulePage />} />
              <Route path="sbom" element={<ModulePage />} />
              <Route path="deception" element={<ModulePage />} />
              <Route path="forensics" element={<ModulePage />} />
              <Route path="itdr" element={<ModulePage />} />
              <Route path="tip" element={<ModulePage />} />
              <Route path="threat-intel" element={<ModulePage />} />
              <Route path="attack-navigator" element={<ModulePage />} />
              <Route path="compliance-continuous" element={<ModulePage />} />
              <Route path="exec-risk" element={<ModulePage />} />
              <Route path="ai-agent" element={<ModulePage />} />
              <Route path="agent-chat" element={<AgentChatPage />} />
              <Route path="compliance" element={<CompliancePage />} />
              <Route path="profile" element={<Profile />} />
              <Route path="account" element={<Account />} />
              <Route
                path="admin"
                element={
                  <RequireAuth
                    allowedRoles={["ADMIN"]}
                    allowedPermissions={["users:manage", "audit:read"]}
                    roles={userRoles}
                    permissions={userPermissions}
                  />
                }
              >
                <Route index element={<AdminDashboard />} />
                <Route path="users" element={<AdminUsers />} />
                <Route path="tenants" element={<TenantsPage />} />
                <Route path="roles" element={<AccessRolesPage />} />
                <Route path="rules" element={<RulesPage />} />
                <Route path="reputation" element={<ReputationPage />} />
                <Route path="engine-settings" element={<AdminEngineSettings />} />
                <Route path="system-logs" element={<AdminAuditLogs />} />
                <Route path="sso" element={<SsoScimPage />} />
                <Route path="apikeys" element={<ApiKeysPage />} />
                <Route path="compliance" element={<CompliancePage />} />
              </Route>
            </Route>
          </Route>

          <Route path="/unauthorized" element={<Navigate to="/alerts" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    </Router>
  );
}
