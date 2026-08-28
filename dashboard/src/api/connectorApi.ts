import { api } from "./axios";
import type { ConnectorConfig, ConnectorConfigInput } from "../types/analyst";

/**
 * Connector configuration + push-ingest webhook.
 *
 * Configuring a source has real side effects (it can write alerts), so the
 * backend gates it on `alerts:write` and audits every change. The outbound
 * credential is write-only: the API never returns it, only whether one is set.
 */

export const fetchConfigs = async (): Promise<ConnectorConfig[]> => {
  const { data } = await api.get<ConnectorConfig[]>("/connectors");
  return data;
};

export const fetchConfig = async (connectorId: string): Promise<ConnectorConfig> => {
  const { data } = await api.get<ConnectorConfig>(`/connectors/${connectorId}/config`);
  return data;
};

export const saveConfig = async (
  connectorId: string,
  payload: ConnectorConfigInput
): Promise<ConnectorConfig> => {
  const { data } = await api.put<ConnectorConfig>(
    `/connectors/${connectorId}/config`,
    payload
  );
  return data;
};

export const deleteConfig = async (
  connectorId: string
): Promise<{ status: string; connector_id: string }> => {
  const { data } = await api.delete<{ status: string; connector_id: string }>(
    `/connectors/${connectorId}/config`
  );
  return data;
};

/** The webhook a source posts events to (push mode). */
export const webhookUrl = (connectorId: string): string =>
  `${window.location.origin}/api/v1/connectors/ingest/${connectorId}`;

export const ConnectorApi = {
  fetchConfigs,
  fetchConfig,
  saveConfig,
  deleteConfig,
  webhookUrl,
};

export default ConnectorApi;
