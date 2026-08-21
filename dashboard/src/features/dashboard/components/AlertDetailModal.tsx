import React from "react";

interface Props {
  alert: any;
  onClose: () => void;
}

const severityBadge: Record<string, string> = {
  CRITICAL: "bg-status-critical/15 text-status-critical border-status-critical/30",
  HIGH: "bg-status-warning/15 text-status-warning border-status-warning/30",
  MEDIUM: "bg-chart-4/15 text-chart-4 border-chart-4/30",
  LOW: "bg-status-success/15 text-status-success border-status-success/30",
};

const bandBadge: Record<string, string> = {
  malicious: "bg-status-critical/15 text-status-critical border-status-critical/30",
  suspicious: "bg-status-warning/15 text-status-warning border-status-warning/30",
  low: "bg-status-success/15 text-status-success border-status-success/30",
  unknown: "bg-app-subtle text-content-secondary border-line-subtle",
};

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:gap-4 sm:items-start">
      <span className="text-sm font-medium text-content-tertiary sm:w-32 shrink-0">{label}</span>
      <div className="flex-1 text-sm text-content-primary min-w-0">{children}</div>
    </div>
  );
}

export default function AlertDetailModal({ alert, onClose }: Props) {
  if (!alert) return null;

  const severity = String(alert.severity || alert.risk || "LOW").toUpperCase();
  const threatIntel: Record<string, unknown> | null | undefined = alert.threat_intel;
  const hasMitre =
    alert.mitre_tactic || alert.mitre_technique_id || alert.mitre_technique;
  const hasThreatIntel = threatIntel && Object.keys(threatIntel).length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-app-surface w-full max-w-2xl rounded-xl p-6 shadow-2xl border border-line-subtle max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-1">
          <h3 className="text-lg font-semibold text-content-primary">Alert Details</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-content-tertiary hover:text-content-primary text-xl leading-none"
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 mb-5">
          <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border ${severityBadge[severity] || severityBadge.LOW}`}>
            {severity}
          </span>
          {alert.alert_type && (
            <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border bg-app-subtle text-content-secondary border-line-subtle">
              {alert.alert_type}
            </span>
          )}
          {alert.id != null && (
            <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-mono border bg-accent-primary/10 text-accent-primary border-accent-primary/30">
              Alert #{alert.id}
            </span>
          )}
        </div>

        <div className="space-y-4">
          <DetailRow label="Source IP">
            <span className="font-mono text-xs text-accent-primary">{alert.source_ip || "N/A"}</span>
          </DetailRow>
          <DetailRow label="Score">
            {alert.score != null ? Number(alert.score).toFixed(3) : "N/A"}
          </DetailRow>
          <DetailRow label="Timestamp">
            <span className="text-xs text-content-secondary">{alert.created_at || alert.timestamp || "N/A"}</span>
          </DetailRow>

          <div>
            <h4 className="text-sm font-semibold text-content-primary mb-2">MITRE ATT&amp;CK</h4>
            {hasMitre ? (
              <div className="flex flex-wrap gap-2">
                <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border bg-app-subtle text-content-primary border-line-subtle">
                  {alert.mitre_tactic}
                </span>
                {alert.mitre_technique_id && (
                  <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-mono border bg-accent-primary/10 text-accent-primary border-accent-primary/30">
                    {alert.mitre_technique_id}
                  </span>
                )}
                {alert.mitre_technique && (
                  <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border bg-app-subtle text-content-secondary border-line-subtle">
                    {alert.mitre_technique}
                  </span>
                )}
              </div>
            ) : (
              <p className="text-xs text-content-tertiary">Unclassified — no MITRE mapping for this alert.</p>
            )}
          </div>

          <div>
            <h4 className="text-sm font-semibold text-content-primary mb-2">Threat intelligence</h4>
            {hasThreatIntel ? (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border ${bandBadge[String(threatIntel.reputation_band || "unknown")] || bandBadge.unknown}`}>
                    {String(threatIntel.reputation_band || "unknown")}
                  </span>
                  <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border bg-app-subtle text-content-secondary border-line-subtle">
                    {String(threatIntel.category || "observed")}
                  </span>
                  {threatIntel.is_blocked ? (
                    <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border bg-status-critical/15 text-status-critical border-status-critical/30">
                      Blocked
                    </span>
                  ) : null}
                </div>
                {typeof threatIntel.threat_score === "number" && (
                  <p className="text-xs text-content-tertiary">
                    Reputation score: <span className="text-content-primary font-mono">{threatIntel.threat_score.toFixed(3)}</span>
                    {threatIntel.ip_address ? (
                      <span> for <span className="font-mono text-accent-primary">{String(threatIntel.ip_address)}</span></span>
                    ) : null}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-xs text-content-tertiary">No reputation context for the source address.</p>
            )}
          </div>

          <div>
            <h4 className="text-sm font-semibold text-content-primary mb-2">Message</h4>
            <pre className="whitespace-pre-wrap bg-app-bg border border-line-subtle p-3 rounded-lg mt-1 text-xs text-content-primary">
              {alert.message || alert.raw_log || alert.raw || ""}
            </pre>
          </div>
        </div>

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-accent-primary text-app-bg text-sm font-medium hover:opacity-90 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}