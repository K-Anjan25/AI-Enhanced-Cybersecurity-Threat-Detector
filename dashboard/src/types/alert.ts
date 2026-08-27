export type ThreatSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

/**
 * Shape returned by the backend's /alerts endpoints (serialize_alert):
 * {id, alert_type, source_ip, source, severity, score, message,
 *  mitre_tactic, mitre_technique_id, mitre_technique, threat_intel, created_at}
 */
export interface Alert {
  id: number;
  alert_type: string | null;
  source_ip: string | null;
  source: string | null;
  severity: ThreatSeverity | string | null;
  score: number | null;
  message: string | null;
  mitre_tactic?: string | null;
  mitre_technique_id?: string | null;
  mitre_technique?: string | null;
  threat_intel?: Record<string, unknown> | null;
  created_at: string | null;
}

export interface ScannedThreat {
  ruleName: string;
  severity: ThreatSeverity;
  details: string;
  rawLog?: string;
}

export interface UploadLogsResponse {
  message: string;
  batch_id: number;
  filename?: string;
  totalLogsParsed?: number;
  threatsDetected?: number;
  results?: unknown[];
}

/** Background scan batch status: GET /uploads/{batch_id}. */
export interface UploadBatchStatus {
  batch: {
    id: number;
    filename: string;
    total_logs: number;
    threats_detected: number;
    status: "pending" | "processing" | "completed" | "failed";
    message: string | null;
    created_at: string | null;
  };
}

export interface LogHistoryEntry {
  filename: string;
  batch_id?: number;
  totalLogsParsed: number;
  threatsDetected: number;
  status?: string;
  timestamp: string | null;
}

export interface SaveScannedAlertsResponse {
  message: string;
  savedCount: number;
  alerts: Alert[];
}
