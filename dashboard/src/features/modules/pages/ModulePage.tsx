import React from "react";
import { useLocation } from "react-router-dom";
import FuturePhasesPage from "../../advanced/pages/FuturePhasesPage";
import NextPhasesPage from "../../advanced/pages/NextPhasesPage";
import AdvancedHubPage from "../../advanced/pages/AdvancedHubPage";
import ThreatAlertsPage from "../../alerts/pages/ThreatAlertsPage";

export default function ModulePage() {
  const loc = useLocation();
  const path = loc.pathname;

  // Map path to which hub to show
  if (path.startsWith("/ztna") || path.startsWith("/hunting") || path.startsWith("/vulns") || path.startsWith("/ai-agent")) {
    return <NextPhasesPage />;
  }
  if (path.startsWith("/cspm") || path.startsWith("/sbom") || path.startsWith("/deception") || path.startsWith("/forensics") || path.startsWith("/itdr") || path.startsWith("/tip") || path.startsWith("/compliance-continuous") || path.startsWith("/exec-risk")) {
    return <FuturePhasesPage />;
  }
  if (path.startsWith("/threat-intel") || path.startsWith("/attack-navigator")) {
    return <AdvancedHubPage />;
  }
  return <div className="p-6 text-sm text-content-secondary">Module {path} — view in Advanced Hub</div>;
}
