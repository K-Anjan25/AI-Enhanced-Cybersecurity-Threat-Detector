export type SoarActionStatus = "pending" | "executing" | "executed" | "failed" | "skipped";

export interface SoarAction {
  id: number;
  action_id: string;
  action_type: string;
  severity: string;
  rule_name?: string | null;
  alert_id?: number | null;
  status: SoarActionStatus;
  payload?: Record<string, unknown> | null;
  created_at?: string | null;
}

export interface EvaluateResponse {
  actions: Array<Record<string, unknown>>;
  count: number;
}

export interface TriggerResponse {
  executed: Array<Record<string, unknown>>;
  count: number;
}