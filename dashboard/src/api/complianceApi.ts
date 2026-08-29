import { http } from "./client";

const ComplianceApi = {
  verifyAuditChain: async (limit = 100) => {
    const res = await http.get(`/compliance/audit/verify?limit=${limit}`);
    return res.data as {
      total_checked: number;
      verified: number;
      chain_valid: boolean;
      broken_at: number | null;
      broken_details: string | null;
      last_hash: string;
    };
  },
  getSoc2Evidence: async (days = 90) => {
    const res = await http.get(`/compliance/audit/evidence?days=${days}`);
    return res.data;
  },
  getCaseChain: async (caseId: number) => {
    const res = await http.get(`/compliance/cases/${caseId}/chain-of-custody`);
    return res.data;
  },
};

export default ComplianceApi;
