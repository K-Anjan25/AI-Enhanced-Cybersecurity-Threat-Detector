import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { QueryClient, QueryClientProvider } from "react-query";

import FeedPage from "./FeedPage";
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

const makeCase = (id: number, decision: string = "pending", priority: string = "critical"): AnalystCase =>
  ({
    id,
    title: `Case ${id} headline`,
    description: "what happened",
    priority,
    decision,
    status: "open",
    created_at: new Date().toISOString(),
    analysis: { headline: `Case ${id} headline`, confidence: 0.9, fallback: false, model: "test" },
    proposed_action: { action_type: "REVOKE_CREDENTIALS", target: "account:jdoe", rationale: "test", undo: "undo" },
    blast_radius: { nodes: [], links: [] },
  } as unknown as AnalystCase);

const renderPage = () => {
  const store = configureStore({ reducer: { user: () => ({ user: null, isLoggedIn: true, loading: false, error: null }) } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <Provider store={store}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <FeedPage />
        </MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("FeedPage", () => {
  it("renders cases from the feed and marks pending with threat-item", async () => {
    mocked.fetchFeed.mockResolvedValue({
      data: [makeCase(1, "pending"), makeCase(2, "approved")],
      total: 2,
      page: 1,
      limit: 10,
    } as never);

    renderPage();

    await waitFor(() => expect(screen.getByText("Case 1 headline")).toBeInTheDocument());
    expect(screen.getByText("Case 2 headline")).toBeInTheDocument();

    // pending rows carry SIGNAL vocabulary threat-item
    const rows = document.querySelectorAll("tr.threat-item");
    expect(rows.length).toBe(1);
  });

  it("shows honest empty state when no cases", async () => {
    mocked.fetchFeed.mockResolvedValue({ data: [], total: 0, page: 1, limit: 10 } as never);
    renderPage();
    await waitFor(() => expect(screen.getByText(/no cases yet/i)).toBeInTheDocument());
  });

  it("survives bare array response (defensive)", async () => {
    mocked.fetchFeed.mockResolvedValue([makeCase(1)] as never);
    renderPage();
    await waitFor(() => expect(screen.getByText("Case 1 headline")).toBeInTheDocument());
  });
});
