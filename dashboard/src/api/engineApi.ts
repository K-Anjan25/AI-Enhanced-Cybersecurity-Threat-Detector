import { api } from "./axios";
import type {
  EngineSettings,
  SettingsResponse,
  UpdateEngineSettingsPayload,
} from "../types/engine";

/**
 * Fetches the current threat detection engine settings
 */
export const getEngineSettings = async (): Promise<EngineSettings> => {
  try {
    const response = await api.get<EngineSettings>("/engine/settings");
    return response.data;
  } catch (error: any) {
    throw error.response?.data || error.message;
  }
};

/**
 * Updates the threat detection engine settings
 */
export const updateEngineSettings = async (
  settingsData: UpdateEngineSettingsPayload
): Promise<SettingsResponse> => {
  try {
    const response = await api.put<SettingsResponse>(
      "/engine/settings",
      settingsData
    );
    return response.data;
  } catch (error: any) {
    throw error.response?.data || error.message;
  }
};

export const EngineApi = {
  getEngineSettings,
  updateEngineSettings,
};

export default EngineApi;