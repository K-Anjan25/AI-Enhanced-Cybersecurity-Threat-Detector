import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AnalystApi from "../../../api/analystApi";
import { Term } from "../../../components/ui";

interface Props {
  alert: any;
  onClose: () => void;
}

const severityBadge: Record<string, string> = {
  CRITICAL: "bg-severity-critical/15 text-severity-critical border-severity-critical/30",
  HIGH: "bg-severity-high/15 text-severity-high border-severity-high/30",
  MEDIUM: "bg-severity-medium/15 text-severity-medium border-severity-medium/30",
  LOW: "bg-severity-low/15 text-severity-low border-severity-low/30",
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
  const [linkedCaseId, setLinkedCaseId] = useState<number | null>(null);

  // Bridge to the analyst workflow: if a NOCTRA case was opened from this
  // alert, offer a direct link (best-effort lookup over the decision feed).
  useEffect(() => {
    let alive = true;
    if (alert?.id == null) return;
    AnalystApi.fetchFeed({ page: 1, limit: 100 })
      .then((res) => {
        if (!alive) return;
        const rows = Array.isArray(res) ? res : res?.data ?? [];
        const hit = rows.find((c: { source_alert_id?: number | null }) => c.source_alert_id === alert.id);
        if (hit) setLinkedCaseId(hit.id);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [alert?.id]);

  // Dialog semantics: Escape closes; backdrop click closes.
  useEffect(() => {
    if (alert?.id == null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [alert?.id, onClose]);

  if (!alert) return null;

  const severity = String(alert.severity || alert.risk || "LOW").toUpperCase();
  const threatIntel: Record<string, unknown> | null | undefined = alert.threat_intel;
  const hasMitre =
    alert.mitre_tactic || alert.mitre_technique_id || alert.mitre_technique;
  const hasThreatIntel = threatIntel && Object.keys(threatIntel).length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Alert details${alert.id != null ? ` #${alert.id}` : ""}`}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-app-surface w-full max-w-2xl rounded-2xl p-6 shadow-2xl border border-line-subtle max-h-[90vh] overflow-y-auto">
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
          {linkedCaseId != null && (
            <Link
              to={`/case/${linkedCaseId}`}
              onClick={onClose}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold border bg-accent-primary text-brand-ink border-transparent hover:opacity-90 transition"
            >
              NOCTRA case #{linkedCaseId} →
            </Link>
          )}
        </div>

        <div className="space-y-4">
          <DetailRow label="Source IP">
            <span className="font-mono text-xs text-accent-primary">{alert.source_ip || "N/A"}</span>
          </DetailRow>
          <DetailRow label="Score">
            {alert.score != null && Number.isFinite(Number(alert.score))
              ? Number(alert.score).toFixed(3)
              : "N/A"}
          </DetailRow>
          <DetailRow label="Timestamp">
            <span className="text-xs text-content-secondary">{alert.created_at || alert.timestamp || "N/A"}</span>
          </DetailRow>

          <div>
            <h4 className="text-sm font-semibold text-content-primary mb-2">
              <Term>MITRE</Term> ATT&amp;CK
            </h4>
            {hasMitre ? (
              <div className="flex flex-wrap gap-2">
                <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border bg-app-subtle text-content-primary border-line-subtle">
                  {alert.mitre_tactic}
                </span>
                {alert.mitre_technique_id && (
                  <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-mono border bg-accent-primary/10 text-accent-primary border-accent-primary/30">
                    <Term mono>{alert.mitre_technique_id}</Term>
                  </span>
                )}
                {alert.mitre_technique && (
                  <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border bg-app-subtle text-content-secondary border-line-subtle">
                    {alert.mitre_technique}
                  </span>
                )}
              </div>
            ) : (
              <p className="text-xs text-content-tertiary">
                Unclassified — no <Term>MITRE</Term> mapping for this alert.
              </p>
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
                    <Term>Reputation</Term> score: <span className="text-content-primary font-mono">{threatIntel.threat_score.toFixed(3)}</span>
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
            className="px-4 py-2 rounded-sm bg-brand-gradient text-brand-ink text-sm font-medium hover:-translate-y-0.5 hover:shadow-signal hover:opacity-95 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}