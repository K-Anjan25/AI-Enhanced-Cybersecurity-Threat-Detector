import { api } from "./axios";

export interface StreamTicket {
  ticket: string;
  expires_in: number;
}

export const requestStreamTicket = async (): Promise<string> => {
  const { data } = await api.post<StreamTicket>("/stream/ticket");
  return data.ticket;
};

export const streamUrl = (ticket: string): string => {
  const base = api.defaults.baseURL || "/api/v1";
  // Ensure base doesn't have trailing slash
  const trimmed = base.replace(/\/+$/, "");
  return `${trimmed}/stream/alerts?ticket=${encodeURIComponent(ticket)}`;
};

export const fetchStreamStatus = async (): Promise<{ process_scoped: boolean; subscriber_count: number; queue_size: number; heartbeat_seconds: number; note: string }> => {
  const { data } = await api.get("/stream/status");
  return data;
};
