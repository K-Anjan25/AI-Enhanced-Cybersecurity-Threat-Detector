import { api } from "./axios";

export interface DetectionRule {
  id: number;
  name: string;
  description?: string | null;
  severity: string;
  pattern?: string | null;
  is_active: boolean;
  created_at?: string | null;
}

export interface PaginatedRules {
  data: DetectionRule[];
  total: number;
  page: number;
  limit: number;
}

export const fetchRules = async (page = 1, limit = 100): Promise<PaginatedRules> => {
  const { data } = await api.get<PaginatedRules>("/rules", { params: { page, limit } });
  return data;
};

export const createRule = async (payload: {
  name: string;
  description?: string;
  severity?: string;
  pattern?: string;
  is_active?: boolean;
}): Promise<DetectionRule> => {
  const { data } = await api.post<DetectionRule>("/rules", payload);
  return data;
};

export const updateRule = async (
  ruleId: number,
  payload: Partial<{
    name: string;
    description?: string;
    severity?: string;
    pattern?: string;
    is_active?: boolean;
  }>
): Promise<DetectionRule> => {
  const { data } = await api.put<DetectionRule>(`/rules/${ruleId}`, payload);
  return data;
};

export const deleteRule = async (ruleId: number): Promise<{ success: boolean }> => {
  const { data } = await api.delete(`/rules/${ruleId}`);
  return data;
};

export const RulesApi = { fetchRules, createRule, updateRule, deleteRule };

export default RulesApi;