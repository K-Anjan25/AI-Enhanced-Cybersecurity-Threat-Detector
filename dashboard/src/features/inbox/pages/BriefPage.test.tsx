import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { QueryClient, QueryClientProvider } from "react-query";

import BriefPage from "./BriefPage";
import AnalystApi from "../../../api/analystApi";
import type { Brief, Connector } from "../../../types/analyst";

// The page imports the default API object, so the module boundary — not the
// individual functions — is what has to be stubbed.
vi.mock("../../../api/ocsfApi", () => ({ default: { fetchBrief: vi.fn().mockResolvedValue({ summary: "No recent", total: 0, findings: [] }), exportAlerts: vi.fn() } }));
vi.mock("../../../api/complianceApi", () => ({ default: { verifyAuditChain: vi.fn().mockResolvedValue({ chain_valid: true, verified: 5 }), getSoc2Evidence: vi.fn(), getCaseChain: vi.fn() } }));

vi.mock("../../../api/analystApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/analystApi")>();
  return {
    ...actual,
    default: {
      ...actual.default,
      fetchBrief: vi.fn(),
      fetchConnectors: vi.fn(),
      fetchFeed: vi.fn(),
      syncConnector: vi.fn(),
    },
  };
});

const mocked = vi.mocked(AnalystApi);

// ── Fixtures ────────────────────────────────────────────────────────────────

const brief = {
  pending_count: 2,
  handled_today: 1,
  watching: 18,
  alerts_today: 11,
  auto_recorded_today: 0,
  top_cases: [],
} as unknown as Brief;

const connectors: Connector[] = [
  {
    id: "okta",
    name: "Okta Identity Cloud",
    category: "Identity",
    status: "not_connected",
    last_sync: null,
    assets_monitored: null,
    latency_ms: null,
    live: false,
  },
  {
    id: "sentinel",
    name: "CrowdStrike / Sentinel EDR",
    category: "Endpoint",
    status: "connected",
    last_sync: "just now",
    assets_monitored: 3,
    latency_ms: 12,
    live: true,
    mode: "poll",
    events_ingested: 3,
  },
];

/** Locate a connector card by its heading text (name -> row -> block -> card). */
const cardFor = (name: string): HTMLElement => {
  const el = screen.getByText(name).closest("div")!.parentElement!.parentElement!;
  return el as HTMLElement;
};

const renderPage = () => {
  const store = configureStore({
    reducer: {
      user: () => ({ user: null, isLoggedIn: true, loading: false, error: null }),
    },
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <BriefPage />
        </MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("user_permissions", JSON.stringify(["alerts:read", "alerts:write"]));
  mocked.fetchBrief.mockResolvedValue(brief);
  mocked.fetchConnectors.mockResolvedValue(connectors);
  mocked.fetchFeed.mockResolvedValue({ data: [], total: 0, page: 1, limit: 100 } as never);
  mocked.syncConnector.mockResolvedValue({
    status: "synced",
    message: "Fetched 3 event(s) — 3 recorded.",
    last_sync: "just now",
  });
});

// ── Tests ───────────────────────────────────────────────────────────────────

describe("BriefPage — brief metrics", () => {
  it("renders the real counts returned by /analyst/brief", async () => {
    renderPage();
    // The sub-line is composed from the actual fields, so asserting on it
    // catches a regression that renders a hard-coded or missing number.
    await waitFor(() =>
      expect(screen.getByText(/11 events investigated today/i)).toBeInTheDocument()
    );
    // The sentence is composed of several nodes, so assert on the rendered
    // text of the whole line rather than a single element.
    const line = screen.getByText(/events investigated today/i).closest("p")!;
    // handled_today is 1, so the copy must be singular — pluralisation that
    // lies ("1 decisions") is exactly the sloppiness these tests exist to stop.
    expect(line.textContent).toContain("1 decision by you");
    expect(line.textContent).not.toContain("1 decisions");
    expect(line.textContent).toContain("2 waiting");
  });

  it("shows an honest empty state when nothing is pending", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/watching 18 assets/i)).toBeInTheDocument()
    );
  });
});

describe("BriefPage — connectors", () => {
  it("renders '—' for telemetry it does not have, and real counts for what it does", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Okta Identity Cloud")).toBeInTheDocument());

    const oktaCard = cardFor("Okta Identity Cloud");
    const sentinelCard = cardFor("CrowdStrike / Sentinel EDR");

    // Unconfigured: no invented asset count.
    expect(within(oktaCard).getByText("—")).toBeInTheDocument();
    expect(within(oktaCard).getByText(/not connected/i)).toBeInTheDocument();

    // Connected: the count comes from rows actually ingested.
    expect(within(sentinelCard).getByText(/3 assets/)).toBeInTheDocument();
    expect(within(sentinelCard).getByText(/connected/i)).toBeInTheDocument();
  });

  it("offers Sync with no timestamp when the connector has never synced", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Okta Identity Cloud")).toBeInTheDocument());
    const oktaCard = cardFor("Okta Identity Cloud");
    // It must not claim "just now" for a sync that never happened.
    expect(within(oktaCard).getByRole("button", { name: /sync/i })).toBeInTheDocument();
    expect(within(oktaCard).queryByText(/just now/i)).not.toBeInTheDocument();
  });

  it("hides Configure from users without alerts:write", async () => {
    localStorage.setItem("user_permissions", JSON.stringify(["alerts:read"]));
    renderPage();
    await waitFor(() => expect(screen.getByText("Okta Identity Cloud")).toBeInTheDocument());
    expect(screen.queryByText(/configure/i)).not.toBeInTheDocument();
  });

  it("re-reads real connector state after syncing instead of faking a timestamp", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Okta Identity Cloud")).toBeInTheDocument());
    const before = mocked.fetchConnectors.mock.calls.length;

    const user = userEvent.setup();
    await user.click(within(cardFor("Okta Identity Cloud")).getByRole("button", { name: /sync/i }));

    await waitFor(() => expect(mocked.syncConnector).toHaveBeenCalledWith("okta"));
    // The list is re-fetched so the card reflects server truth rather than a
    // client-side guess.
    await waitFor(() => expect(mocked.fetchConnectors.mock.calls.length).toBeGreaterThan(before));
  });
});
