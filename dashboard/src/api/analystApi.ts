import { api } from "./axios";
import type {
  AnalystCase,
  Brief,
  ReportResponse,
  Connector,
  TimelineResponse,
  NotificationsResponse,
} from "../types/analyst";
import type { PaginatedResponse } from "../types/pagination";

export interface FeedParams {
  page: number;
  limit: number;
}

/** Calm home-screen summary: pending decisions, handled today, assets watched. */
export interface ScenarioDef {
  id: string;
  label: string;
  mitre: string;
  severity: string;
  description: string;
}

export const fetchScenarios = async (): Promise<ScenarioDef[]> => {
  const { data } = await api.get<{ data: ScenarioDef[] }>("/analyst/scenarios");
  // Back-compat: endpoint may return {data: [...]} or direct array
  if (Array.isArray((data as any).data)) return (data as any).data;
  return data as unknown as ScenarioDef[];
};

export const exportCase = async (id: number | string): Promise<{ case: AnalystCase; timeline: any[]; exported_at: string; exported_by: string }> => {
  const { data } = await api.get(`/analyst/cases/${id}/export`);
  return data;
};

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

/** Inject a simulated scenario (default credential_leak). */
export const simulate = async (scenarioType: string = "credential_leak"): Promise<AnalystCase> => {
  const { data } = await api.post<AnalystCase>(`/analyst/simulate?scenario_type=${encodeURIComponent(scenarioType)}`);
  return data;
};

export const chatAboutCase = async (id: number | string, message: string): Promise<{ answer: string; confidence: number }> => {
  const { data } = await api.post<{ answer: string; confidence: number }>(`/analyst/cases/${id}/chat`, { message });
  return data;
};

export const fetchConnectors = async (): Promise<Connector[]> => {
  const { data } = await api.get<Connector[]>("/analyst/connectors");
  return data;
};

export interface SyncConnectorResult {
  /** "recorded" when no live source is configured — never a fake "success". */
  status: string;
  message: string;
  live?: boolean;
  last_sync?: string | null;
}

export const syncConnector = async (connectorId: string): Promise<SyncConnectorResult> => {
  const { data } = await api.post<SyncConnectorResult>(`/analyst/connectors/${connectorId}/sync`);
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

/** Server-side case record: entries composed from real rows only. */
export const fetchTimeline = async (id: number | string): Promise<TimelineResponse> => {
  const { data } = await api.get<TimelineResponse>(`/analyst/cases/${id}/timeline`);
  return data;
};

/** Derived notifications: pending decisions + outcomes from the last 24 h. */
export const fetchNotifications = async (): Promise<NotificationsResponse> => {
  const { data } = await api.get<NotificationsResponse>("/analyst/notifications");
  return data;
};

export const AnalystApi = {
  fetchBrief,
  fetchFeed,
  fetchCase,
  simulate,
  fetchScenarios,
  exportCase,
  chatAboutCase,
  fetchConnectors,
  syncConnector,
  approveCase,
  declineCase,
  revertCase,
  fetchReport,
  fetchTimeline,
  fetchNotifications,
};

export default AnalystApi;
