import { api } from "./axios";

export type AuditVerify = {
  total_checked: number;
  verified: number;
  chain_valid: boolean;
  broken_at?: number;
  broken_details?: string;
  last_hash: string;
};

export type Soc2Bundle = {
  generated_at: string;
  period_days: number;
  total_logs: number;
  chain_integrity: AuditVerify;
  controls: Record<string, { control_name: string; description: string; evidence_count: number; sample_logs: { action: string; actor: string; resource: string; timestamp: string }[] }>;
};

export type ChainOfCustody = {
  case_id: number;
  title: string;
  chain: { at: string; kind: string; label: string; detail: string; hash: string; prev_hash: string }[];
  last_hash: string;
  verified: boolean;
};

export const fetchAuditVerify = async (limit = 1000): Promise<AuditVerify> => {
  const { data } = await api.get<AuditVerify>("/compliance/audit/verify", { params: { limit } });
  return data;
};

export const fetchSoc2Evidence = async (days = 90): Promise<Soc2Bundle> => {
  const { data } = await api.get<Soc2Bundle>("/compliance/audit/evidence", { params: { days } });
  return data;
};

export const fetchChainOfCustody = async (caseId: number): Promise<ChainOfCustody> => {
  const { data } = await api.get<ChainOfCustody>(`/compliance/cases/${caseId}/chain-of-custody`);
  return data;
};

export const fetchEvidenceBundle = async (caseId: number): Promise<any> => {
  const { data } = await api.get(`/compliance/cases/${caseId}/evidence-bundle`);
  return data;
};

export const downloadEvidencePdf = async (caseId: number, includeSoc2 = false): Promise<Blob> => {
  const { data } = await api.get(`/compliance/cases/${caseId}/evidence-bundle/pdf`, {
    responseType: "blob",
    params: { include_soc2: includeSoc2 },
  });
  return data;
};

export const downloadSoc2Pdf = async (days = 90): Promise<Blob> => {
  const { data } = await api.get(`/compliance/audit/evidence/pdf`, {
    responseType: "blob",
    params: { days },
  });
  return data;
};

export const ComplianceApi = {
  fetchAuditVerify,
  fetchSoc2Evidence,
  fetchChainOfCustody,
  fetchEvidenceBundle,
  downloadEvidencePdf,
  downloadSoc2Pdf,
};

export default ComplianceApi;
