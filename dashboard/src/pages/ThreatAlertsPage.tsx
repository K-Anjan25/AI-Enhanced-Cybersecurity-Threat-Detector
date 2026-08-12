import React from "react";
import AlertList from "../features/dashboard/components/AlertList";

const ThreatAlertsPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">Threat Alerts</h1>
          <p className="text-sm text-content-secondary mt-1">
            Review detected threats and save critical alerts for investigation.
          </p>
        </div>
      </header>

      <AlertList />
    </div>
  );
};

export default ThreatAlertsPage;
