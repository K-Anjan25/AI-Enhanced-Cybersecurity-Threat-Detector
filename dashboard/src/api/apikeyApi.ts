import { api } from "./axios";

export type ApiKeyInfo = {
  id: number;
  org_id: number;
  name: string;
  prefix: string;
  last4: string;
  scopes: string;
  is_active: boolean;
  created_by_user_id?: number;
  service_account_id?: number;
  expires_at?: string;
  last_used_at?: string;
  created_at?: string;
  revoked_at?: string;
};

export type ServiceAccountInfo = {
  id: number;
  org_id: number;
  user_id: number;
  name: string;
  description?: string;
  is_active: boolean;
  created_by_user_id?: number;
  created_at?: string;
  username?: string;
  role?: string;
};

export type RateLimitStatus = {
  org_id: number;
  enabled: boolean;
  rps_limit: number;
  burst_limit: number;
  current_rps: number;
  current_per_minute: number;
  backend: string;
};

export const fetchApiKeys = async (): Promise<ApiKeyInfo[]> => {
  const { data } = await api.get<ApiKeyInfo[]>("/apikeys");
  return data;
};

export const createApiKey = async (payload: { name: string; scopes?: string; expires_days?: number; service_account_id?: number }): Promise<ApiKeyInfo & { raw_key: string; warning: string }> => {
  const { data } = await api.post("/apikeys", payload);
  return data;
};

export const revokeApiKey = async (id: number): Promise<any> => {
  const { data } = await api.delete(`/apikeys/${id}`);
  return data;
};

export const fetchServiceAccounts = async (): Promise<ServiceAccountInfo[]> => {
  const { data } = await api.get<ServiceAccountInfo[]>("/apikeys/service-accounts");
  return data;
};

export const createServiceAccount = async (payload: { name: string; description?: string; role?: string }): Promise<ServiceAccountInfo> => {
  const { data } = await api.post("/apikeys/service-accounts", payload);
  return data;
};

export const revokeServiceAccount = async (id: number): Promise<any> => {
  const { data } = await api.delete(`/apikeys/service-accounts/${id}`);
  return data;
};

export const fetchRateLimitStatus = async (): Promise<RateLimitStatus> => {
  const { data } = await api.get<RateLimitStatus>("/apikeys/rate-limit/status");
  return data;
};

export const ApiKeyApi = {
  fetchApiKeys,
  createApiKey,
  revokeApiKey,
  fetchServiceAccounts,
  createServiceAccount,
  revokeServiceAccount,
  fetchRateLimitStatus,
};

export default ApiKeyApi;
