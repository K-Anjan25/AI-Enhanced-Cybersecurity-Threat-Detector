import { api } from "./axios";
import type {
  Alert,
  LogHistoryEntry,
  SaveScannedAlertsResponse,
  ScannedThreat,
  UploadLogsResponse,
} from "../types/alert";

/**
 * Fetches the list of all detected security alerts
 */
export const fetchAlerts = async (): Promise<Alert[]> => {
  const response = await api.get<Alert[]>("/alerts");
  return response.data;
};

/**
 * Uploads log files for automated threat scanning
 */
export const uploadLogs = async (file: File): Promise<UploadLogsResponse> => {
  const formData = new FormData();
  formData.append("log_file", file);

  const response = await api.post<UploadLogsResponse>("/upload-logs", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
};

export const fetchLogHistory = async (): Promise<LogHistoryEntry[]> => {
  const response = await api.get<{ logs: LogHistoryEntry[] }>("/logs/history");
  return response.data.logs || [];
};

/**
 * Saves scanned threat entries as system alerts
 */
export const saveScannedAlerts = async (
  threats: ScannedThreat[]
): Promise<SaveScannedAlertsResponse> => {
  const response = await api.post<SaveScannedAlertsResponse>("/save-scanned-alerts", {
    threats,
  });
  return response.data;
};

export const AlertApi = {
  fetchAlerts,
  uploadLogs,
  saveScannedAlerts,
};

export default AlertApi;