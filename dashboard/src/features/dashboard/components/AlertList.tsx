import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { fetchAlerts } from "../../../api/alertApi";
import AlertDetailModal from "./AlertDetailModal";
import { SeverityBadge, SkeletonTable, EmptyState } from "../../../components/ui";
import { Select } from "../../../components/ui/Select";

interface AlertListProps {
  extraAlerts?: any[];
  onSelectAlert?: (alert: any) => void;
  onAlertsFetched?: (alerts: any[]) => void;
}

const AlertList: React.FC<AlertListProps> = ({ extraAlerts = [], onSelectAlert, onAlertsFetched }) => {
  const [searchParams] = useSearchParams();
  const [alerts, setAlerts] = useState<any[]>([]);
  const [search, setSearch] = useState<string>(() => searchParams.get("q") ?? "");
  const [riskFilter, setRiskFilter] = useState<string>("All");
  const [selectedAlert, setSelectedAlert] = useState<any | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 8;

  useEffect(() => {
    const loadAlerts = () => {
      fetchAlerts()
        .then((data: any) => {
          const payload: any = data;
          const list = Array.isArray(payload) ? payload : payload?.items || [];
          setAlerts(list);
          setLoading(false);

          if (onAlertsFetched) {
            onAlertsFetched(list);
          }
        })
        .catch((err) => {
          console.error("Error loading alerts:", err);
          setLoading(false);
        });
    };

    loadAlerts();
    const interval = setInterval(loadAlerts, 60000);
    return () => clearInterval(interval);
  }, [onAlertsFetched]);

  const getSeverity = (alert: any) => {
    if (!alert) return "LOW";
    const sev = alert.severity || alert.risk || "LOW";
    return String(sev).trim().toUpperCase();
  };

  const getMessage = (alert: any) => {
    if (!alert) return "";
    return String(alert.message || alert.raw_log || alert.raw || alert.type || "");
  };

  const allAlerts = [...extraAlerts, ...alerts];

  const filteredAlerts = allAlerts.filter((alert) => {
    const sev = getSeverity(alert);
    const matchesRisk = riskFilter === "All" || sev === riskFilter.toUpperCase();
    const matchesSearch = getMessage(alert).toLowerCase().includes(search.toLowerCase());

    return matchesRisk && matchesSearch;
  });

  const totalItems = filteredAlerts.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / itemsPerPage));
  const validPage = Math.min(currentPage, totalPages);
  const startIndex = (validPage - 1) * itemsPerPage;
  const currentPaginatedItems = filteredAlerts.slice(startIndex, startIndex + itemsPerPage);

  const handleRowClick = (alert: any) => {
    setSelectedAlert(alert);
    if (typeof onSelectAlert === "function") {
      onSelectAlert(alert);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-content-primary tracking-tight">Security Alerts</h2>
          <p className="text-xs text-content-tertiary mt-0.5">Real-time threat log detections and severity breakdowns.</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative w-full sm:w-64">
            <input
              type="text"
              placeholder="Search alerts…"
              className="w-full pl-3 pr-4 py-2 bg-app-bg border border-line-subtle rounded-lg text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary transition"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCurrentPage(1);
              }}
            />
          </div>

          <Select
            inline
            className="min-w-[140px]"
            value={riskFilter}
            onChange={(e) => {
              setRiskFilter(e.target.value);
              setCurrentPage(1);
            }}
            aria-label="Filter by severity"
            options={[
              { value: "All", label: "All Risks" },
              { value: "Critical", label: "Critical" },
              { value: "High", label: "High" },
              { value: "Medium", label: "Medium" },
              { value: "Low", label: "Low" },
            ]}
          />
        </div>
      </div>

      <div className="bg-app-surface rounded-2xl border border-line-subtle shadow-card overflow-hidden">
        {loading ? (
          <SkeletonTable rows={6} cols={3} checkbox bare />
        ) : currentPaginatedItems.length === 0 ? (
          <EmptyState
            title="No security alerts found matching your criteria"
            description="Try clearing filters or uploading logs to generate detections."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
                  <th scope="col" className="px-5 py-3.5 w-44">Timestamp</th>
                  <th scope="col" className="px-5 py-3.5">Log Message / Content</th>
                  <th scope="col" className="px-5 py-3.5 w-40">Severity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-subtle text-sm">
                {currentPaginatedItems.map((alert, index) => {
                  const sev = getSeverity(alert);
                  const msg = getMessage(alert);
                  return (
                    <tr
                      key={alert.id || startIndex + index}
                      onClick={() => handleRowClick(alert)}
                      className="hover:bg-app-subtle/50 cursor-pointer transition-colors group"
                    >
                      <td className="px-5 py-4 font-mono text-xs text-content-tertiary whitespace-nowrap">
                        {alert.created_at || alert.timestamp || "N/A"}
                      </td>
                      <td className="px-5 py-4 font-mono text-xs text-accent-primary max-w-xl truncate group-hover:opacity-80">
                        {msg}
                      </td>
                      <td className="px-5 py-4 whitespace-nowrap">
                        <SeverityBadge severity={sev} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {!loading && allAlerts.length > 0 && (
          <div className="flex flex-col sm:flex-row justify-between items-center px-5 py-3.5 bg-app-surface border-t border-line-subtle text-xs text-content-secondary gap-3">
            <div>
              Showing <span className="text-content-primary font-medium">{totalItems === 0 ? 0 : startIndex + 1}</span> to{" "}
              <span className="text-content-primary font-medium">{Math.min(startIndex + itemsPerPage, totalItems)}</span> of{" "}
              <span className="text-content-primary font-medium">{totalItems}</span> alerts
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={validPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1.5 bg-app-subtle hover:bg-line-bright border border-line-subtle text-content-secondary rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Previous
              </button>

              <span className="px-2 text-content-secondary font-medium">{validPage} / {totalPages}</span>

              <button
                type="button"
                disabled={validPage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                className="px-3 py-1.5 bg-app-subtle hover:bg-line-bright border border-line-subtle text-content-secondary rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {selectedAlert && (
        <AlertDetailModal
          alert={selectedAlert}
          onClose={() => setSelectedAlert(null)}
        />
      )}
    </div>
  );
};

export default AlertList;