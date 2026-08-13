import { api } from "./axios";
import type { EntityGraphResponse, EntityType, ThreatEntity } from "../types/entity";
import type { PaginatedResponse } from "../types/pagination";

export interface EntityListParams {
  page: number;
  limit: number;
  entity_type?: EntityType;
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

export const EntityApi = {
  fetchEntities,
  fetchEntityGraph,
  updateEntityRisk,
};

export default EntityApi;