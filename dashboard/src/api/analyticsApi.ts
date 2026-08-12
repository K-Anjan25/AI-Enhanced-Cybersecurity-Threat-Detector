import { api } from "./axios";
import type { OverviewStats, TopThreat, TrendsResponse } from "../types/analytics";

export const getAnalyticsOverview = async (): Promise<OverviewStats> => {
  const { data } = await api.get<OverviewStats>("/analytics/overview");
  return data;
};

export const getTopThreats = async (limit = 10): Promise<TopThreat[]> => {
  const { data } = await api.get<TopThreat[]>("/analytics/top-threats", {
    params: { limit },
  });
  return data;
};

export const getAlertTrends = async (days = 7): Promise<TrendsResponse> => {
  const { data } = await api.get<TrendsResponse>("/analytics/trends", {
    params: { days },
  });
  return data;
};

export const AnalyticsApi = {
  getOverview: getAnalyticsOverview,
  getTopThreats,
  getAlertTrends,
};

export default AnalyticsApi;
