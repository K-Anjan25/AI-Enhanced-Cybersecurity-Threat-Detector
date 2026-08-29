import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "react-query";
import { MemoryRouter } from "react-router-dom";

import SsoScimPage from "./SsoScimPage";
import * as ssoApi from "../../../api/ssoApi";
import "../../../api/client";

vi.mock("../../../api/ssoApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/ssoApi")>();
  return {
    ...actual,
    fetchSsoProviders: vi.fn(),
    fetchScimTokens: vi.fn(),
    upsertSsoProvider: vi.fn(),
    deleteSsoProvider: vi.fn(),
    createScimToken: vi.fn(),
    deleteScimToken: vi.fn(),
  };
});

vi.mock("../../../api/client", () => ({
  http: {
    get: vi.fn().mockResolvedValue({ data: { data: [] } }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

const mocked = vi.mocked(ssoApi);

const renderPage = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SsoScimPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  mocked.fetchSsoProviders.mockResolvedValue({
    org: { enabled: false } as any,
    global: { enabled: false } as any,
  });
  mocked.fetchScimTokens.mockResolvedValue({ data: [] } as any);
});

describe("SsoScimPage", () => {
  it("renders SSO and SCIM sections", async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/Single Sign-On/i).length).toBeGreaterThan(0));
    expect(screen.getByText(/SCIM 2.0 Provisioning/i)).toBeInTheDocument();
  });

  it("shows empty state for SCIM tokens", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/No SCIM tokens/i)).toBeInTheDocument());
  });

  it("renders existing SCIM tokens", async () => {
    mocked.fetchScimTokens.mockResolvedValue({
      data: [{ id: 1, name: "Okta SCIM", prefix: "scim_abc", created_at: new Date().toISOString(), is_active: true }],
    } as any);
    renderPage();
    await waitFor(() => expect(screen.getByText(/Okta SCIM/)).toBeInTheDocument());
  });
});
