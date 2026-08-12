export type ThreatSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Alert {
  id: string;
  title: string;
  description: string;
  severity: ThreatSeverity;
  sourceIp?: string;
  timestamp: string;
  status?: "NEW" | "INVESTIGATING" | "RESOLVED";
}

export interface ScannedThreat {
  ruleName: string;
  severity: ThreatSeverity;
  details: string;
  rawLog?: string;
}

export interface UploadLogsResponse {
  message: string;
  filename?: string;
  totalLogsParsed?: number;
  threatsDetected?: number;
  results?: unknown[];
}

export interface LogHistoryEntry {
  filename: string;
  totalLogsParsed: number;
  threatsDetected: number;
  timestamp: string;
  results: unknown[];
}

export interface SaveScannedAlertsResponse {
  message: string;
  savedCount: number;
  alerts: Alert[];
}
