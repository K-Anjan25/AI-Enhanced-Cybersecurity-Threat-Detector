export interface SeverityDistribution {
  CRITICAL: number;
  HIGH: number;
  MEDIUM: number;
  LOW: number;
}

export interface OverviewStats {
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  severity_distribution: SeverityDistribution;
  by_type: Record<string, number>;
  recent: Array<{
    id: number;
    message: string;
    severity: string;
    created_at?: string | null;
  }>;
}

export interface TopThreat {
  threat: string;
  count: number;
}

export interface TrendPoint {
  date: string;
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface TrendsResponse {
  days: number;
  trend: TrendPoint[];
}
