import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ConnectorConfigModal from "./ConnectorConfigModal";
import ConnectorApi from "../../api/connectorApi";
import type { Connector } from "../../types/analyst";

vi.mock("../../api/connectorApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/connectorApi")>();
  return {
    ...actual,
    default: {
      ...actual.default,
      fetchConfig: vi.fn(),
      saveConfig: vi.fn(),
      deleteConfig: vi.fn(),
      webhookUrl: (id: string) => `/api/v1/connectors/ingest/${id}`,
    },
  };
});

const mocked = vi.mocked(ConnectorApi);

const connector: Connector = {
  id: "okta",
  name: "Okta Identity Cloud",
  category: "Identity",
  status: "not_connected",
  live: false,
  last_sync: null,
  assets_monitored: null,
  latency_ms: null,
  events_ingested: 0,
};

beforeEach(() => {
  vi.clearAllMocks();
  mocked.fetchConfig.mockRejectedValue(new Error("no config"));
  mocked.saveConfig.mockResolvedValue({} as never);
  mocked.deleteConfig.mockResolvedValue({} as never);
});

describe("ConnectorConfigModal", () => {
  it("shows push mode with webhook and secret field when no config exists", async () => {
    render(<ConnectorConfigModal open connector={connector} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Configure Okta Identity Cloud/)).toBeInTheDocument());
    expect(screen.getByText(/Shared secret/i)).toBeInTheDocument();
    // Webhook appears as code element containing POST
    await waitFor(() => expect(screen.getByText(/POST.*\/api\/v1\/connectors\/ingest\/okta/)).toBeInTheDocument());
  });

  it("never shows stored secret value — only has_*_token boolean", async () => {
    mocked.fetchConfig.mockResolvedValue({
      connector_id: "okta",
      mode: "push",
      enabled: true,
      has_ingest_token: true,
      has_auth_token: false,
      events_ingested: 0,
    } as never);

    render(<ConnectorConfigModal open connector={connector} onClose={() => {}} onSaved={() => {}} />);

    await waitFor(() => expect(screen.getByPlaceholderText(/Stored — leave blank to keep/)).toBeInTheDocument());
    // The actual secret must never appear in DOM
    expect(screen.queryByText(/supersecret/)).not.toBeInTheDocument();
  });

  it("switches to poll mode and shows endpoint field", async () => {
    render(<ConnectorConfigModal open connector={connector} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Configure Okta/)).toBeInTheDocument());

    const user = userEvent.setup();
    // Select is a custom component — find by label and change
    const select = screen.getByLabelText(/Delivery mode/i) as HTMLSelectElement;
    await user.selectOptions(select, "poll");

    expect(screen.getByLabelText(/Events endpoint/i)).toBeInTheDocument();
    expect(screen.queryByText(/Shared secret/i)).not.toBeInTheDocument();
  });

  it("save sends only non-empty fields and does not wipe secrets with blank", async () => {
    render(<ConnectorConfigModal open connector={connector} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Configure Okta/)).toBeInTheDocument());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Save configuration/i }));

    await waitFor(() => expect(mocked.saveConfig).toHaveBeenCalled());
    const payload = mocked.saveConfig.mock.calls[0][1] as any;
    expect(payload.mode).toBe("push");
    expect(payload.auth_token).toBeUndefined();
    expect(payload.ingest_token).toBeUndefined();
  });
});
