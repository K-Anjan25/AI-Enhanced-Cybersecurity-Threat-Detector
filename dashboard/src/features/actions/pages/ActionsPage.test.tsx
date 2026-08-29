import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { QueryClient, QueryClientProvider } from "react-query";

import ActionsPage from "./ActionsPage";
import AnalystApi from "../../../api/analystApi";
import type { AnalystCase } from "../../../types/analyst";

vi.mock("../../../api/analystApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/analystApi")>();
  return {
    ...actual,
    default: {
      ...actual.default,
      fetchFeed: vi.fn(),
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
    status: decision === "approved" ? "resolved" : "triaging",
    created_at: new Date().toISOString(),
    decided_at: new Date().toISOString(),
    soar_action_id: `soar-${id}`,
    analysis: { headline: `Case ${id}`, confidence: 0.9, fallback: false, model: "claude" },
    proposed_action: { action_type: "BLOCK_SOURCE_IP", target: "ip:1.2.3.4", rationale: "r", undo: "u" },
    blast_radius: { nodes: [], links: [] },
  } as unknown as AnalystCase);

const renderPage = () => {
  const store = configureStore({ reducer: { user: () => ({ user: null }) } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <Provider store={store}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ActionsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
};

beforeEach(() => vi.clearAllMocks());

describe("ActionsPage", () => {
  it("renders only approved/reverted cases and shows record-only language", async () => {
    mocked.fetchFeed.mockResolvedValue({
      data: [makeCase(1, "approved"), makeCase(2, "reverted"), makeCase(3, "pending")],
      total: 3,
      page: 1,
      limit: 100,
    } as never);

    renderPage();

    await waitFor(() => expect(screen.getByText(/Actions Log/)).toBeInTheDocument());
    // pending must be filtered out — only approved/reverted
    await waitFor(() => expect(screen.getByText("Case #1")).toBeInTheDocument());
    expect(screen.getByText("Case #2")).toBeInTheDocument();
    expect(screen.queryByText("Case #3")).not.toBeInTheDocument();

    // Record-only language is present
    expect(screen.getAllByText(/record-only/i).length).toBeGreaterThan(0);
  });

  it("shows empty state when no recorded actions", async () => {
    mocked.fetchFeed.mockResolvedValue({ data: [], total: 0, page: 1, limit: 100 } as never);
    renderPage();
    await waitFor(() => expect(screen.getByText(/No recorded actions/i)).toBeInTheDocument());
  });
});
