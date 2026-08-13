import { api } from "./axios";
import type { EvaluateResponse, SoarAction, TriggerResponse } from "../types/soar";
import type { PaginatedResponse } from "../types/pagination";

export interface SoarActionListParams {
  page: number;
  limit: number;
}

export const fetchSoarActions = async (
  params: SoarActionListParams
): Promise<PaginatedResponse<SoarAction>> => {
  const { data } = await api.get<PaginatedResponse<SoarAction>>("/soar/actions", { params });
  return data;
};

export const evaluateAlert = async (
  alert: Record<string, unknown>
): Promise<EvaluateResponse> => {
  const { data } = await api.post<EvaluateResponse>("/soar/evaluate", alert);
  return data;
};

export const triggerForAlert = async (alertId: number): Promise<TriggerResponse> => {
  const { data } = await api.post<TriggerResponse>(`/soar/trigger/${alertId}`);
  return data;
};

export const SoarApi = {
  fetchActions: fetchSoarActions,
  evaluateAlert,
  triggerForAlert,
};

export default SoarApi;