import { api } from "./axios";
import type {
  Alert,
  LogHistoryEntry,
  SaveScannedAlertsResponse,
  ScannedThreat,
  UploadBatchStatus,
  UploadLogsResponse,
} from "../types/alert";

/**
 * Fetches detected security alerts (server returns {items,total,page,limit}).
 * Requests the maximum page size so client-side pagination/filtering sees the
 * full alert list, not just the API default of 20 rows.
 */
export const fetchAlerts = async (page = 1, limit = 100): Promise<Alert[]> => {
  const response = await api.get<{ items: Alert[]; total: number; page: number; limit: number }>(
    "/alerts",
    { params: { page, limit } }
  );
  return response.data.items ?? [];
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
 * Polls the status of a background scan batch (used to surface the real
 * threats-detected count after an upload finishes processing).
 */
export const fetchUploadBatchStatus = async (
  batchId: number
): Promise<UploadBatchStatus> => {
  const response = await api.get<UploadBatchStatus>(
    `/uploads/${batchId}`
  );
  return response.data;
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
  fetchUploadBatchStatus,
  saveScannedAlerts,
};

export default AlertApi;