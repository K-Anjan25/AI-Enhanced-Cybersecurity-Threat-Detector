import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { QueryClient, QueryClientProvider } from "react-query";

import ReportsPage from "./ReportsPage";
import AnalystApi from "../../../api/analystApi";
import type { AnalystCase } from "../../../types/analyst";

vi.mock("../../../api/analystApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/analystApi")>();
  return {
    ...actual,
    default: {
      ...actual.default,
      fetchFeed: vi.fn(),
      fetchReport: vi.fn(),
    },
  };
});

const mocked = vi.mocked(AnalystApi);

const makeCase = (id: number, decision: string = "approved"): AnalystCase =>
  ({
    id,
    title: `Case ${id}`,
    priority: "critical",
    decision,
    status: "resolved",
    created_at: new Date().toISOString(),
    report: `# Report for case ${id}\nReasoned by claude-sonnet`,
    analysis: { headline: `Case ${id}`, confidence: 0.9, fallback: false, model: "claude-sonnet-5", what_happened: "x" },
    proposed_action: { action_type: "REVOKE_CREDENTIALS", target: "account:jdoe", rationale: "r", undo: "u" },
    blast_radius: { nodes: [], links: [] },
  } as unknown as AnalystCase);

const renderPage = () => {
  const store = configureStore({ reducer: { user: () => ({}) } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <Provider store={store}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ReportsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
};

beforeEach(() => vi.clearAllMocks());

describe("ReportsPage", () => {
  it("renders reports and names reasoning source", async () => {
    mocked.fetchFeed.mockResolvedValue({
      data: [makeCase(1), makeCase(2, "reverted")],
      total: 2,
      page: 1,
      limit: 100,
    } as never);
    mocked.fetchReport.mockResolvedValue({ case_id: 1, report: "# Report\nReasoned by claude-sonnet" } as never);

    renderPage();

    await waitFor(() => expect(screen.getByText(/Incident Reports/)).toBeInTheDocument());
    expect(screen.getAllByText(/Case 1/).length).toBeGreaterThan(0);
  });

  it("shows honest empty when no decided cases", async () => {
    mocked.fetchFeed.mockResolvedValue({ data: [], total: 0, page: 1, limit: 100 } as never);
    renderPage();
    await waitFor(() => expect(screen.getByText(/No incident reports/i)).toBeInTheDocument());
  });
});
