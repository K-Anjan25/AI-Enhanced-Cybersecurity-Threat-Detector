import { api } from "./axios";

export interface IpReputationEntry {
  id?: number | null;
  ip_address: string;
  threat_score: number;
  is_blocked: boolean;
  category?: string | null;
  notes?: string | null;
  updated_at?: string | null;
}

export interface PaginatedReputation {
  data: IpReputationEntry[];
  total: number;
  page: number;
  limit: number;
}

export const fetchReputation = async (page = 1, limit = 100): Promise<PaginatedReputation> => {
  const { data } = await api.get<PaginatedReputation>("/reputation", { params: { page, limit } });
  return data;
};

export const upsertReputation = async (payload: {
  ip_address: string;
  threat_score?: number;
  is_blocked?: boolean;
  category?: string;
  notes?: string;
}): Promise<IpReputationEntry> => {
  const { data } = await api.post<IpReputationEntry>("/reputation", payload);
  return data;
};

export const blockIp = async (ipAddress: string): Promise<IpReputationEntry> => {
  const { data } = await api.post<IpReputationEntry>(`/reputation/${encodeURIComponent(ipAddress)}/block`);
  return data;
};

export const unblockIp = async (ipAddress: string): Promise<IpReputationEntry> => {
  const { data } = await api.post<IpReputationEntry>(`/reputation/${encodeURIComponent(ipAddress)}/unblock`);
  return data;
};

export const ReputationApi = {
  fetchReputation,
  upsertReputation,
  blockIp,
  unblockIp,
};

export default ReputationApi;