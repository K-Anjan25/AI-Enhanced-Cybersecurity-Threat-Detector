import React from "react";
import AlertList from "../../../features/dashboard/components/AlertList";
import { PageHeader } from "../../../components/ui";

const ThreatAlertsPage: React.FC = () => {
  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Threat Alerts"
        description="Review detected threats and save critical alerts for investigation."
      />

      <AlertList />
    </div>
  );
};

export default ThreatAlertsPage;
