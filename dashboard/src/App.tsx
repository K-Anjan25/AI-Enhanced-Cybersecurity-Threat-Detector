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
const AdvancedHubPage = React.lazy(() => import("./features/advanced/pages/AdvancedHubPage"));
const NextPhasesPage = React.lazy(() => import("./features/advanced/pages/NextPhasesPage"));
const FuturePhasesPage = React.lazy(() => import("./features/advanced/pages/FuturePhasesPage"));
const AdvancedPhasesPage = React.lazy(() => import("./features/advanced/pages/AdvancedPhasesPage"));
const FinalPhasesPage = React.lazy(() => import("./features/advanced/pages/FinalPhasesPage"));
const SOCWallPage = React.lazy(() => import("./features/advanced/pages/SOCWallPage"));
const UltraPhasesPage = React.lazy(() => import("./features/advanced/pages/UltraPhasesPage"));
const FederatedAutopilotPage = React.lazy(() => import("./features/advanced/pages/FederatedAutopilotPage"));
const Final10Page = React.lazy(() => import("./features/advanced/pages/Final10Page"));
const Beyond100Page = React.lazy(() => import("./features/advanced/pages/Beyond100Page"));
const MetaSingularityPage = React.lazy(() => import("./features/advanced/pages/MetaSingularityPage"));
const OmniSingularityPage = React.lazy(() => import("./features/advanced/pages/OmniSingularityPage"));
const TranscendencePage = React.lazy(() => import("./features/advanced/pages/TranscendencePage"));
const AbsoluteInfinityPage = React.lazy(() => import("./features/advanced/pages/AbsoluteInfinityPage"));
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
              <Route path="advanced" element={<AdvancedHubPage />} />
              <Route path="next" element={<NextPhasesPage />} />
              <Route path="future" element={<FuturePhasesPage />} />
              <Route path="advanced-phases" element={<AdvancedPhasesPage />} />
              <Route path="final-phases" element={<FinalPhasesPage />} />
              <Route path="ultra-phases" element={<UltraPhasesPage />} />
              <Route path="federated-autopilot" element={<FederatedAutopilotPage />} />
              <Route path="soc-tv-wall" element={<SOCWallPage />} />
              <Route path="data-lake" element={<AdvancedPhasesPage />} />
              <Route path="marketplace" element={<AdvancedPhasesPage />} />
              <Route path="finetune" element={<AdvancedPhasesPage />} />
              <Route path="risk-based" element={<AdvancedPhasesPage />} />
              <Route path="purple-team" element={<AdvancedPhasesPage />} />
              <Route path="pdf-export" element={<AdvancedPhasesPage />} />
              <Route path="attack-coverage" element={<FinalPhasesPage />} />
              <Route path="agent-collab" element={<FinalPhasesPage />} />
              <Route path="approval-workflows" element={<UltraPhasesPage />} />
              <Route path="hunt-notebooks" element={<UltraPhasesPage />} />
              <Route path="exposure" element={<UltraPhasesPage />} />
              <Route path="ai-redteam" element={<UltraPhasesPage />} />
              <Route path="federated" element={<FederatedAutopilotPage />} />
              <Route path="compliance-autopilot" element={<FederatedAutopilotPage />} />
              <Route path="final10" element={<Final10Page />} />
              <Route path="federated-intel" element={<Final10Page />} />
              <Route path="quantum-safe" element={<Final10Page />} />
              <Route path="attack-path" element={<Final10Page />} />
              <Route path="cart" element={<Final10Page />} />
              <Route path="data-fabric" element={<Final10Page />} />
              <Route path="soc-manager" element={<Final10Page />} />
              <Route path="drp" element={<Final10Page />} />
              <Route path="cnapp" element={<Final10Page />} />
              <Route path="posture-score" element={<Final10Page />} />
              <Route path="noctra-os" element={<Final10Page />} />
              <Route path="beyond100" element={<Beyond100Page />} />
              <Route path="global-federation" element={<Beyond100Page />} />
              <Route path="predictive-soc" element={<Beyond100Page />} />
              <Route path="hunt-swarm" element={<Beyond100Page />} />
              <Route path="digital-twin" element={<Beyond100Page />} />
              <Route path="quantum-comms" element={<Beyond100Page />} />
              <Route path="ai-governance" element={<Beyond100Page />} />
              <Route path="supply-chain-v2" element={<Beyond100Page />} />
              <Route path="xr-soc" element={<Beyond100Page />} />
              <Route path="deception-grid" element={<Beyond100Page />} />
              <Route path="self-healing" element={<Beyond100Page />} />
              <Route path="meta-singularity" element={<MetaSingularityPage />} />
              <Route path="incident-commander" element={<MetaSingularityPage />} />
              <Route path="insurance-risk" element={<MetaSingularityPage />} />
              <Route path="actor-dna" element={<MetaSingularityPage />} />
              <Route path="data-vault" element={<MetaSingularityPage />} />
              <Route path="compliance-auditor-v2" element={<MetaSingularityPage />} />
              <Route path="neural-copilot" element={<MetaSingularityPage />} />
              <Route path="intel-mesh" element={<MetaSingularityPage />} />
              <Route path="adversary-llm" element={<MetaSingularityPage />} />
              <Route path="blockchain-audit" element={<MetaSingularityPage />} />
              <Route path="meta-os" element={<MetaSingularityPage />} />
              <Route path="omni-singularity" element={<OmniSingularityPage />} />
              <Route path="interplanetary-soc" element={<OmniSingularityPage />} />
              <Route path="agi-council" element={<OmniSingularityPage />} />
              <Route path="legislation-engine" element={<OmniSingularityPage />} />
              <Route path="synthetic-universe" element={<OmniSingularityPage />} />
              <Route path="holographic-soc" element={<OmniSingularityPage />} />
              <Route path="autonomous-workforce" element={<OmniSingularityPage />} />
              <Route path="consciousness-monitor" element={<OmniSingularityPage />} />
              <Route path="planetary-defense" element={<OmniSingularityPage />} />
              <Route path="time-prophecy" element={<OmniSingularityPage />} />
              <Route path="omni-os" element={<OmniSingularityPage />} />
              <Route path="transcendence" element={<TranscendencePage />} />
              <Route path="multiverse-soc" element={<TranscendencePage />} />
              <Route path="quantum-consciousness" element={<TranscendencePage />} />
              <Route path="autonomous-economy" element={<TranscendencePage />} />
              <Route path="neuro-symbolic" element={<TranscendencePage />} />
              <Route path="self-replicating" element={<TranscendencePage />} />
              <Route path="temporal-defense" element={<TranscendencePage />} />
              <Route path="universal-language" element={<TranscendencePage />} />
              <Route path="infinite-learning" element={<TranscendencePage />} />
              <Route path="existential-risk" element={<TranscendencePage />} />
              <Route path="transcendence-os" element={<TranscendencePage />} />
              <Route path="absolute-infinity" element={<AbsoluteInfinityPage />} />
              <Route path="omniversal-soc" element={<AbsoluteInfinityPage />} />
              <Route path="reality-fabric" element={<AbsoluteInfinityPage />} />
              <Route path="chrono-loop" element={<AbsoluteInfinityPage />} />
              <Route path="unified-consciousness" element={<AbsoluteInfinityPage />} />
              <Route path="void-defense" element={<AbsoluteInfinityPage />} />
              <Route path="genesis-protocol" element={<AbsoluteInfinityPage />} />
              <Route path="akashic-ledger" element={<AbsoluteInfinityPage />} />
              <Route path="cosmic-threat" element={<AbsoluteInfinityPage />} />
              <Route path="dimensional-barrier" element={<AbsoluteInfinityPage />} />
              <Route path="absolute-os" element={<AbsoluteInfinityPage />} />
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
