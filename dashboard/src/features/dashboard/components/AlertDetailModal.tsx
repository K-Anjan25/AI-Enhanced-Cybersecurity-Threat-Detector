import React from "react";

interface Props {
  alert: any;
  onClose: () => void;
}

export default function AlertDetailModal({ alert, onClose }: Props) {
  if (!alert) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-app-surface w-full max-w-2xl rounded-xl p-6 shadow-2xl border border-line-subtle">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-content-primary">Alert Details</h3>
          <button onClick={onClose} className="text-content-tertiary hover:text-content-primary">&times;</button>
        </div>

        <div className="space-y-3 text-sm text-content-secondary">
          <div>
            <strong className="text-content-primary">Severity:</strong> {alert.severity || alert.risk}
          </div>
          <div>
            <strong className="text-content-primary">Source:</strong> {alert.source || alert.source_ip || "N/A"}
          </div>
          <div>
            <strong className="text-content-primary">Message:</strong>
            <pre className="whitespace-pre-wrap bg-app-bg p-2 rounded mt-1 text-xs text-content-primary">{alert.message || alert.raw_log || alert.raw || ""}</pre>
          </div>
          <div>
            <strong className="text-content-primary">Timestamp:</strong> {alert.created_at || alert.timestamp || "N/A"}
          </div>
        </div>

        <div className="mt-4 text-right">
          <button onClick={onClose} className="px-3 py-1.5 bg-accent-primary text-app-bg rounded-lg">Close</button>
        </div>
      </div>
    </div>
  );
}
