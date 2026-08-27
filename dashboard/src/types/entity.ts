export type EntityType = "ip" | "domain" | "hash" | "email" | "file" | "account" | "host";

export interface ThreatEntity {
  id: number;
  entity_type: EntityType;
  value: string;
  risk_score: number;
  occurrences: number;
  meta?: Record<string, unknown> | null;
  first_seen?: string | null;
  last_seen?: string | null;
}

export interface GraphLink {
  source: number;
  target: number;
  relation: string;
}

export interface EntityGraphResponse {
  root: number | null;
  nodes: ThreatEntity[];
  links: GraphLink[];
}