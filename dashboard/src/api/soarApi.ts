import { api } from "./axios";
import type {
  EvaluateResponse,
  SoarAction,
  SoarPlaybook,
  TriggerResponse,
} from "../types/soar";
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

export const fetchPlaybooks = async (
  params: SoarActionListParams
): Promise<PaginatedResponse<SoarPlaybook>> => {
  const { data } = await api.get<PaginatedResponse<SoarPlaybook>>("/soar/playbooks", { params });
  return data;
};

export const createPlaybook = async (
  payload: { rule_id: number; name: string; action_type: string }
): Promise<SoarPlaybook> => {
  const { data } = await api.post<SoarPlaybook>("/soar/playbooks", payload);
  return data;
};

export const updatePlaybook = async (
  id: number,
  payload: Partial<Pick<SoarPlaybook, "name" | "action_type" | "is_active">>
): Promise<SoarPlaybook> => {
  const { data } = await api.patch<SoarPlaybook>(`/soar/playbooks/${id}`, payload);
  return data;
};

export const deletePlaybook = async (id: number): Promise<{ deleted: boolean }> => {
  const { data } = await api.delete<{ deleted: boolean }>(`/soar/playbooks/${id}`);
  return data;
};

export const SoarApi = {
  fetchActions: fetchSoarActions,
  evaluateAlert,
  triggerForAlert,
  fetchPlaybooks,
  createPlaybook,
  updatePlaybook,
  deletePlaybook,
};

export default SoarApi;