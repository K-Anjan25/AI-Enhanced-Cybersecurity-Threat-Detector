import { http } from "./client";

const OcsfApi = {
  fetchBrief: async (limit = 50) => {
    const res = await http.get(`/ocsf/brief?limit=${limit}`);
    return res.data as { summary: string; findings: any[]; total: number };
  },
  exportAlerts: async (params: { limit?: number; severity?: string; source?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.severity) qs.set("severity", params.severity);
    if (params.source) qs.set("source", params.source);
    const res = await http.get(`/ocsf/alerts?${qs.toString()}`);
    return res.data;
  },
};

export default OcsfApi;
