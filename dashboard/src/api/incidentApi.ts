import { api } from "./axios";
import type {
  CreateIncidentPayload,
  Incident,
  UpdateIncidentPayload,
} from "../types/incident";
import type { PaginatedResponse } from "../types/pagination";

export interface IncidentListParams {
  page: number;
  limit: number;
  status?: string;
}

export const fetchIncidents = async (
  params: IncidentListParams
): Promise<PaginatedResponse<Incident>> => {
  const { data } = await api.get<PaginatedResponse<Incident>>("/cases", { params });
  return data;
};

export const fetchIncident = async (caseId: number): Promise<Incident> => {
  const { data } = await api.get<Incident>(`/cases/${caseId}`);
  return data;
};

export const createIncident = async (
  payload: CreateIncidentPayload
): Promise<Incident> => {
  const { data } = await api.post<Incident>("/cases", payload);
  return data;
};

export const updateIncident = async (
  caseId: number,
  payload: UpdateIncidentPayload
): Promise<Incident> => {
  const { data } = await api.patch<Incident>(`/cases/${caseId}`, payload);
  return data;
};

export const IncidentApi = {
  fetchIncidents,
  fetchIncident,
  createIncident,
  updateIncident,
};

export default IncidentApi;