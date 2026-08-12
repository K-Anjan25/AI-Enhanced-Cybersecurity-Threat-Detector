export type ColumnAlignment = "left" | "center" | "right" | "justify";

export interface TableColumn<TKeys = string> {
  id: TKeys;
  label: string;
  minWidth?: number;
  align?: ColumnAlignment;
}

export type ThreatAlertColumnKeys =
  | "id"
  | "ipAddress"
  | "threatType"
  | "severity"
  | "status"
  | "timestamp";

export type UserColumnKeys =
  | "id"
  | "username"
  | "email"
  | "role"
  | "status";

export const THREAT_ALERT_COLUMNS: TableColumn<ThreatAlertColumnKeys>[] = [
  { id: "id", label: "Alert ID", minWidth: 80 },
  { id: "ipAddress", label: "Source IP", minWidth: 120 },
  { id: "threatType", label: "Threat Type", minWidth: 140 },
  { id: "severity", label: "Severity", minWidth: 100, align: "center" },
  { id: "status", label: "Status", minWidth: 100 },
  { id: "timestamp", label: "Detected At", minWidth: 150 },
];

export const USER_COLUMNS: TableColumn<UserColumnKeys>[] = [
  { id: "id", label: "User ID", minWidth: 70 },
  { id: "username", label: "Username", minWidth: 120 },
  { id: "email", label: "Email Address", minWidth: 180 },
  { id: "role", label: "Role", minWidth: 100 },
  { id: "status", label: "Status", minWidth: 100 },
];