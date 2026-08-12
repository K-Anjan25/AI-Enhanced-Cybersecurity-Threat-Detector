export interface EngineSettings {
  detectionSensitivity: "LOW" | "MEDIUM" | "HIGH";
  maxConcurrentScans: number;
  autoQuarantine: boolean;
  kafkaEnabled: boolean;
  logRetentionDays: number;
}

export interface UpdateEngineSettingsPayload {
  detectionSensitivity?: "LOW" | "MEDIUM" | "HIGH";
  maxConcurrentScans?: number;
  autoQuarantine?: boolean;
  kafkaEnabled?: boolean;
  logRetentionDays?: number;
}

export interface SettingsResponse {
  message: string;
  settings: EngineSettings;
}
