import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { QueryClient, QueryClientProvider } from "react-query";

import CasePage from "./CasePage";
import AnalystApi from "../../../api/analystApi";
import * as alertApi from "../../../api/alertApi";

vi.mock("../../../api/analystApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/analystApi")>();
  return {
    ...actual,
    default: {
      ...actual.default,
      fetchCase: vi.fn(),
      fetchTimeline: vi.fn(),
      chatAboutCase: vi.fn(),
      approveCase: vi.fn(),
      declineCase: vi.fn(),
      revertCase: vi.fn(),
      exportCase: vi.fn(),
    },
  };
});

vi.mock("../../../api/alertApi", () => ({
  fetchAlerts: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../../api/axios", async (importOriginal) => {
  const actual = await importOriginal<any>();
  return {
    ...actual,
    api: {
      ...actual.api,
      get: vi.fn().mockResolvedValue({ data: new Blob(["%PDF"], { type: "application/pdf" }) }),
    },
  };
});

const mocked = vi.mocked(AnalystApi);
const mockedAlerts = vi.mocked(alertApi);

const baseCase = {
  id: 1,
  title: "Leaked credential in use",
  description: "what happened",
  priority: "critical",
  decision: "pending",
  status: "open",
  created_at: new Date().toISOString(),
  source_alert_id: 10,
  analysis: {
    headline: "Leaked credential in use",
    what_happened: "A credential leaked",
    why_it_matters: "It matters",
    blast_radius_summary: "2 assets",
    confidence: 0.9,
    model: "fallback-template",
    fallback: true,
  },
  proposed_action: {
    action_type: "REVOKE_CREDENTIALS",
    target: "account:jdoe",
    rationale: "Contain",
    undo: "Re-enable account",
  },
  blast_radius: {
    root_entity_id: 1,
    nodes: [
      { id: 1, entity_type: "email", value: "jdoe@acme.com", risk_score: 1 },
      { id: 2, entity_type: "account", value: "jdoe", risk_score: 1 },
    ],
    links: [{ source: 1, target: 2, relation: "derives_from" }],
  },
  report: null,
  soar_action_id: null,
} as any;

const renderPage = () => {
  const store = configureStore({ reducer: { user: () => ({}) } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <Provider store={store}>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/case/1"]}>
          <Routes>
            <Route path="/case/:id" element={<CasePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  mocked.fetchCase.mockResolvedValue(baseCase);
  mocked.fetchTimeline.mockResolvedValue({ case_id: 1, entries: [{ at: new Date().toISOString(), kind: "opened", label: "Case opened", detail: "x" }] } as never);
  mocked.chatAboutCase.mockResolvedValue({ answer: "test answer", confidence: 0.9 } as never);
  mocked.exportCase.mockResolvedValue({ case: baseCase, timeline: [], exported_at: new Date().toISOString(), exported_by: "demo" } as never);
  mockedAlerts.fetchAlerts.mockResolvedValue([]);
});

describe("CasePage", () => {
  it("renders headline, blast radius and reversible action", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument());
    expect(screen.getByText(/Blast radius/)).toBeInTheDocument();
    expect(screen.getByText(/REVOKE_CREDENTIALS/)).toBeInTheDocument();
    expect(screen.getAllByText(/Reversible/).length).toBeGreaterThan(0);
  });

  it("shows fallback reasoning label when analysis is templated", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/built-in reasoning engine/i)).toBeInTheDocument());
  });

  it("renders timeline entries from server", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/Case record/)).toBeInTheDocument());
    expect(screen.getAllByText(/Case opened/).length).toBeGreaterThan(0);
  });

  it("has export button that triggers download", async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/Export JSON/).length).toBeGreaterThan(0));
  });

  it("has Export PDF button", async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/Export PDF/).length).toBeGreaterThan(0));
  });

  it("shows 409 message when PDF not ready", async () => {
    const { api } = await import("../../../api/axios");
    vi.mocked(api.get).mockRejectedValue({ response: { status: 409 } });
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/Export PDF/).length).toBeGreaterThan(0));
    const btn = screen.getAllByText(/Export PDF/)[0];
    btn.click();
    await waitFor(() => expect(screen.getByText(/No report yet/)).toBeInTheDocument());
  });

  it("shows 501 message when PDF renderer missing", async () => {
    const { api } = await import("../../../api/axios");
    vi.mocked(api.get).mockRejectedValue({ response: { status: 501 } });
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/Export PDF/).length).toBeGreaterThan(0));
    const btn = screen.getAllByText(/Export PDF/)[0];
    btn.click();
    await waitFor(() => expect(screen.getByText(/not available/)).toBeInTheDocument());
  });
});
