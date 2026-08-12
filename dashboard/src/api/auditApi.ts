import { api } from "./axios";

export interface AuditLogParams {
  page: number;
  limit: number;
  [key: string]: any;
}

export interface AuditLogResponse {
  data: any[];
  total: number;
  page: number;
  limit: number;
}

export const getAuditLogs = async (params: AuditLogParams): Promise<AuditLogResponse> => {
  const { data } = await api.get<AuditLogResponse>("/audit-logs", { params });
  return data;
};

export const AuditApi = {
  getLogs: getAuditLogs,
};

export const auditapi = AuditApi;
export default AuditApi;