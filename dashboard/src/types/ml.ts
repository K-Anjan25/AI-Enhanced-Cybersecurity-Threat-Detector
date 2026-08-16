export interface BenchmarkMetric {
  accuracy?: number;
  precision?: number;
  recall?: number;
  f1?: number;
  observed_outlier_rate?: number;
  expected_contamination?: number;
  mean_decision_score?: number;
  std_decision_score?: number;
}

export interface BenchmarkModel {
  model: string;
  status: string;
  model_type?: string;
  test_samples?: number;
  benchmarked_samples?: number;
  metrics?: BenchmarkMetric;
  artifact?: string;
  reason?: string;
}

export interface BenchmarkReport {
  version?: string;
  run_at?: string;
  models: BenchmarkModel[];
}

export interface ExplanationContribution {
  term: string;
  score: number;
  direction: "attack" | "benign" | "attention";
  source?: string;
}

export interface ExplanationResponse {
  contributions: ExplanationContribution[];
  summary: string;
  method: string;
  model_error?: string | null;
}

export type ExplainKind = "log" | "email" | "network" | "dns";