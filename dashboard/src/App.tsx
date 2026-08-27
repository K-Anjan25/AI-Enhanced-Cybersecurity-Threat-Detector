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

const ThreatAlertsPage = React.lazy(() => import("./pages/ThreatAlertsPage"));
const LogHistoryPage = React.lazy(() => import("./pages/LogHistoryPage"));
const AIAnalyticsPage = React.lazy(() => import("./pages/AIAnalyticsPage"));
const IncidentsPage = React.lazy(() => import("./pages/IncidentsPage"));
const EntitiesPage = React.lazy(() => import("./pages/EntitiesPage"));
const SoarPage = React.lazy(() => import("./pages/SoarPage"));
const DashboardOverviewPage = React.lazy(() => import("./pages/DashboardOverviewPage"));
const BriefPage = React.lazy(() => import("./pages/BriefPage"));
const FeedPage = React.lazy(() => import("./pages/FeedPage"));
const CasePage = React.lazy(() => import("./pages/CasePage"));
const ActionsPage = React.lazy(() => import("./pages/ActionsPage"));
const ReportsPage = React.lazy(() => import("./pages/ReportsPage"));
const AdminDashboard = React.lazy(() => import("./features/admin/pages/AdminDashboard"));
const AdminUsers = React.lazy(() => import("./features/admin/pages/AdminUsers"));
const AdminEngineSettings = React.lazy(() => import("./pages/admin/EngineSettingsPage"));
const AdminAuditLogs = React.lazy(() => import("./pages/admin/SystemLogsPage"));
const TenantsPage = React.lazy(() => import("./pages/admin/TenantsPage"));
const AccessRolesPage = React.lazy(() => import("./pages/admin/AccessRolesPage"));
const RulesPage = React.lazy(() => import("./pages/admin/RulesPage"));
const ReputationPage = React.lazy(() => import("./pages/admin/ReputationPage"));
const LandingPage = React.lazy(() => import("./pages/LandingPage"));

const FallbackLoader: React.FC = () => (
  <div className="flex justify-center items-center h-screen bg-app-bg text-content-secondary font-mono text-sm">
    <div className="flex items-center space-x-2">
      <div className="w-3 h-3 bg-accent-primary rounded-full animate-ping" />
      <span>Loading AXIOM AI...</span>
    </div>
  </div>
);

export default function App(): JSX.Element {
  // Use the RootState exported from the store (not a local redefinition).
  // userSlice state shape: { user, isLoggedIn, loading, error }
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
          {/* Public Routes */}
          <Route path="/welcome" element={<LandingPage />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/reset-password" element={<ResetPassword />} />

          {/* Protected SOC Dashboard Shell */}
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
              </Route>
            </Route>
          </Route>

          {/* Fallback Catch-All */}
          <Route path="/unauthorized" element={<Navigate to="/alerts" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    </Router>
  );
}