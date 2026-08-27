// Types for the autonomous-analyst product surface (Phases 18-19).

export interface RecommendedAction {
  action_type: string;
  target: string;
  rationale?: string;
  undo?: string;
}

export interface Analysis {
  headline: string;
  what_happened: string;
  why_it_matters: string;
  blast_radius_summary: string;
  recommended_action: RecommendedAction;
  confidence: number;
  model: string;
  fallback: boolean;
}

export interface BlastNode {
  id: number;
  entity_type: string;
  value: string;
  risk_score?: number;
  occurrences?: number;
}

export interface BlastLink {
  source: number;
  target: number;
  relation: string;
}

export interface BlastRadius {
  root_entity_id: number | null;
  nodes: BlastNode[];
  links: BlastLink[];
}

export interface ProposedAction {
  action_type: string;
  target: string;
  severity: string;
  rationale?: string;
  undo?: string;
}

export type Decision = "pending" | "approved" | "declined" | "reverted";

export interface AnalystCase {
  id: number;
  title: string;
  description?: string | null;
  status: string;
  priority: string;
  kind: string;
  source_alert_id?: number | null;
  org_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  analysis?: Analysis | null;
  blast_radius?: BlastRadius | null;
  proposed_action?: ProposedAction | null;
  decision: Decision;
  decided_by_id?: number | null;
  decided_at?: string | null;
  soar_action_id?: string | null;
  report?: string | null;
}

export interface Brief {
  pending_count: number;
  handled_today: number;
  watching: number;
  top_cases: AnalystCase[];
}

export interface ReportResponse {
  case_id: number;
  report: string;
}

export interface ChatMessage {
  id: string;
  sender: "user" | "noctra" | "axiom";
  text: string;
  timestamp: string;
  confidence?: number;
}

export interface Connector {
  id: string;
  name: string;
  category: string;
  status: "connected" | "syncing" | "error";
  last_sync: string;
  assets_monitored: number;
  latency_ms: number;
}
