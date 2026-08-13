export type CaseStatus = "open" | "triaging" | "resolved" | "closed";
export type CasePriority = "low" | "medium" | "high" | "critical";

export interface Incident {
  id: number;
  title: string;
  description?: string | null;
  status: CaseStatus;
  priority: CasePriority;
  source_alert_id?: number | null;
  assignee_id?: number | null;
  created_by_id?: number | null;
  org_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CreateIncidentPayload {
  title: string;
  description?: string;
  status?: CaseStatus;
  priority?: CasePriority;
  source_alert_id?: number;
  assignee_id?: number;
}

export interface UpdateIncidentPayload {
  title?: string;
  description?: string;
  status?: CaseStatus;
  priority?: CasePriority;
  assignee_id?: number;
}
