export const SEVERITY_LEVELS = {
  CRITICAL: "CRITICAL",
  HIGH: "HIGH",
  MEDIUM: "MEDIUM",
  LOW: "LOW",
} as const;

export type SeverityLevelKey = keyof typeof SEVERITY_LEVELS;
export type SeverityLevelValue = (typeof SEVERITY_LEVELS)[SeverityLevelKey];


export const ALERT_STATUSES = {
  ACTIVE: "Active",
  INVESTIGATING: "Investigating",
  RESOLVED: "Resolved",
  DISMISSED: "Dismissed",
} as const;

export type AlertStatusKey = keyof typeof ALERT_STATUSES;
export type AlertStatusValue = (typeof ALERT_STATUSES)[AlertStatusKey];