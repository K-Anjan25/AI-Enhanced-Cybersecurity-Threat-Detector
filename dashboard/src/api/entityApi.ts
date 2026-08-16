import { api } from "./axios";
import type { EntityGraphResponse, EntityType, ThreatEntity } from "../types/entity";
import type { PaginatedResponse } from "../types/pagination";

export interface EntityListParams {
  page: number;
  limit: number;
  entity_type?: EntityType;
}

export interface EntityGraphSummary {
  nodes: number;
  edges: number;
  by_type: Record<string, number>;
  top_risk: ThreatEntity[];
  hubs: Array<ThreatEntity & { degree: number }>;
}

export interface EntityPathResult {
  path: ThreatEntity[];
  links: Array<{ source: number; target: number; relation: string }>;
  hops: number | null;
  reachable: boolean;
}

export const fetchEntities = async (
  params: EntityListParams
): Promise<PaginatedResponse<ThreatEntity>> => {
  const { data } = await api.get<PaginatedResponse<ThreatEntity>>("/entities", { params });
  return data;
};

export const fetchEntityGraph = async (
  entityId: number,
  depth: number
): Promise<EntityGraphResponse> => {
  const { data } = await api.get<EntityGraphResponse>(`/entities/${entityId}/graph`, {
    params: { depth },
  });
  return data;
};

export const updateEntityRisk = async (
  entityId: number,
  riskScore: number
): Promise<ThreatEntity> => {
  const { data } = await api.post<ThreatEntity>(`/entities/${entityId}/reputation`, {
    risk_score: riskScore,
  });
  return data;
};

export const fetchEntityGraphSummary = async (): Promise<EntityGraphSummary> => {
  const { data } = await api.get<EntityGraphSummary>("/entities/summary");
  return data;
};

export const fetchEntityPath = async (
  fromId: number,
  toId: number
): Promise<EntityPathResult> => {
  const { data } = await api.get<EntityPathResult>("/entities/path", {
    params: { from_id: fromId, to_id: toId },
  });
  return data;
};

export const EntityApi = {
  fetchEntities,
  fetchEntityGraph,
  fetchEntityGraphSummary,
  fetchEntityPath,
  updateEntityRisk,
};

export default EntityApi;