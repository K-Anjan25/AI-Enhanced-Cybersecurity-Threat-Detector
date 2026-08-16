import { api } from "./axios";
import type {
  BenchmarkReport,
  ExplainKind,
  ExplanationResponse,
} from "../types/ml";

const payloadFor = (kind: ExplainKind, value: string): Record<string, unknown> => {
  switch (kind) {
    case "log":
      return { message: value, level: "ERROR" };
    case "email":
      return { subject: "Re: status", body: value, sender: "unknown@example.com" };
    case "network": {
      const [port, bytes] = value.split(",").map((p) => Number(p.trim()));
      return {
        dst_port: Number.isFinite(port) ? port : 3389,
        bytes: Number.isFinite(bytes) ? bytes : 0,
        duration: 1,
        total_fwd_packets: 1000,
      };
    }
    case "dns":
      return { domain: value, query_type: "A", answer_ips: [] };
  }
};

export const fetchBenchmark = async (): Promise<BenchmarkReport> => {
  const { data } = await api.get<BenchmarkReport>("/ml/benchmark");
  return data;
};

export const explain = async (
  kind: ExplainKind,
  value: string
): Promise<ExplanationResponse> => {
  const { data } = await api.post<ExplanationResponse>(
    `/ml/explain/${kind}`,
    payloadFor(kind, value)
  );
  return data;
};

export const MlApi = {
  fetchBenchmark,
  explain,
};

export default MlApi;