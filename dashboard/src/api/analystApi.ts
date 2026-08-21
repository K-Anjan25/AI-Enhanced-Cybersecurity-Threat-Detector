import { api } from "./axios";
import type { AnalystCase, Brief, ReportResponse } from "../types/analyst";
import type { PaginatedResponse } from "../types/pagination";

export interface FeedParams {
  page: number;
  limit: number;
}

/** Calm home-screen summary: pending decisions, handled today, assets watched. */
export const fetchBrief = async (): Promise<Brief> => {
  const { data } = await api.get<Brief>("/analyst/brief");
  return data;
};

/** Paginated feed of analyst decisions, newest first. */
export const fetchFeed = async (
  params: FeedParams
): Promise<PaginatedResponse<AnalystCase>> => {
  const { data } = await api.get<PaginatedResponse<AnalystCase>>("/analyst/feed", { params });
  return data;
};

export const fetchCase = async (id: number | string): Promise<AnalystCase> => {
  const { data } = await api.get<AnalystCase>(`/analyst/cases/${id}`);
  return data;
};

/** Inject the credential-leak scenario; returns the newly opened case. */
export const simulate = async (): Promise<AnalystCase> => {
  const { data } = await api.post<AnalystCase>("/analyst/simulate");
  return data;
};

export const approveCase = async (id: number | string): Promise<AnalystCase> => {
  const { data } = await api.post<AnalystCase>(`/analyst/cases/${id}/approve`);
  return data;
};

export const declineCase = async (id: number | string): Promise<AnalystCase> => {
  const { data } = await api.post<AnalystCase>(`/analyst/cases/${id}/decline`);
  return data;
};

export const revertCase = async (id: number | string): Promise<AnalystCase> => {
  const { data } = await api.post<AnalystCase>(`/analyst/cases/${id}/revert`);
  return data;
};

export const fetchReport = async (id: number | string): Promise<ReportResponse> => {
  const { data } = await api.get<ReportResponse>(`/analyst/cases/${id}/report`);
  return data;
};

export const AnalystApi = {
  fetchBrief,
  fetchFeed,
  fetchCase,
  simulate,
  approveCase,
  declineCase,
  revertCase,
  fetchReport,
};

export default AnalystApi;
