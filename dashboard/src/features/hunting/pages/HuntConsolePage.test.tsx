import { describe, it, expect, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import HuntConsolePage from "./HuntConsolePage";
import { ToastProvider } from "../../../components/ui/Toast";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../../api/client", () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}));

const renderPage = () =>
  render(
    <ToastProvider>
      <HuntConsolePage />
    </ToastProvider>,
  );

const row = (over: Record<string, unknown> = {}) => ({
  id: 1,
  severity: "CRITICAL",
  source: "okta",
  source_ip: "203.0.113.1",
  message: "Impossible travel for jo@acme.com",
  alert_type: "log",
  mitre_technique_id: "T1078",
  created_at: "2026-02-19T14:26:03Z",
  ...over,
});

const result = (over: Record<string, unknown> = {}) => ({
  query: "severity:CRITICAL",
  result_count: 1,
  results: [row()],
  duration_ms: 12,
  truncated: false,
  limit: 1000,
  unknown_fields: [],
  unsupported: [],
  honest_note: "KQL subset",
  ...over,
});

describe("HuntConsolePage", () => {
  beforeEach(() => {
    cleanup();
    get.mockReset();
    post.mockReset();
    get.mockResolvedValue({ data: [] });
  });

  it("runs a query and shows the matching alerts", async () => {
    post.mockResolvedValue({ data: result() });
    renderPage();

    await userEvent.type(screen.getByLabelText(/hunt query/i), "severity:CRITICAL");
    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));

    expect(await screen.findByText("1 match")).toBeInTheDocument();
    expect(screen.getByText("Impossible travel for jo@acme.com")).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith("/hunts/execute", { query: "severity:CRITICAL" });
  });

  it("runs on Enter without reaching for the button", async () => {
    post.mockResolvedValue({ data: result() });
    renderPage();

    await userEvent.type(screen.getByLabelText(/hunt query/i), "severity:HIGH{Enter}");

    await waitFor(() => expect(post).toHaveBeenCalled());
  });

  it("treats no matches as a real answer, not a failure", async () => {
    post.mockResolvedValue({ data: result({ result_count: 0, results: [] }) });
    renderPage();

    await userEvent.type(screen.getByLabelText(/hunt query/i), "severity:CRITICAL");
    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));

    expect(await screen.findByText(/That is a real answer/)).toBeInTheDocument();
  });

  it("warns when a field name was not recognised", async () => {
    // The dangerous case: the query ran, but not the query the analyst wrote.
    post.mockResolvedValue({
      data: result({ result_count: 0, results: [], unknown_fields: ["hostnmae"] }),
    });
    renderPage();

    await userEvent.type(screen.getByLabelText(/hunt query/i), "hostnmae:fs01");
    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));

    expect(await screen.findByText(/Unrecognised field/)).toBeInTheDocument();
    expect(screen.getByText("hostnmae")).toBeInTheDocument();
    expect(screen.getByText(/searched the message text instead/)).toBeInTheDocument();
  });

  it("warns when a condition was dropped, so results are too broad", async () => {
    post.mockResolvedValue({
      data: result({ unsupported: ["severity>5"] }),
    });
    renderPage();

    await userEvent.type(screen.getByLabelText(/hunt query/i), "severity:>5");
    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));

    expect(await screen.findByText(/Ignored:/)).toBeInTheDocument();
    expect(screen.getByText(/broader than\s+you asked for/)).toBeInTheDocument();
  });

  it("says when the result set was cut short", async () => {
    post.mockResolvedValue({
      data: result({ result_count: 1000, truncated: true, limit: 1000 }),
    });
    renderPage();

    await userEvent.type(screen.getByLabelText(/hunt query/i), "noise");
    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));

    expect(await screen.findByText(/Showing the first 1000/)).toBeInTheDocument();
    expect(screen.getByText(/There may be more matches/)).toBeInTheDocument();
  });

  it("stays quiet when the query was understood completely", async () => {
    post.mockResolvedValue({ data: result() });
    renderPage();

    await userEvent.type(screen.getByLabelText(/hunt query/i), "severity:CRITICAL");
    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));

    await screen.findByText("1 match");
    expect(screen.queryByText(/Unrecognised field/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Showing the first/)).not.toBeInTheDocument();
  });

  it("clears stale results when a run fails", async () => {
    post.mockResolvedValueOnce({ data: result() });
    renderPage();

    await userEvent.type(screen.getByLabelText(/hunt query/i), "severity:CRITICAL");
    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));
    await screen.findByText("1 match");

    // A failed second run must not leave the first answer on screen.
    post.mockRejectedValueOnce({ response: { data: { detail: "query timed out" } } });
    await userEvent.click(screen.getByRole("button", { name: /^run$/i }));

    expect(await screen.findByText("query timed out")).toBeInTheDocument();
    expect(screen.queryByText("1 match")).not.toBeInTheDocument();
  });

  it("will not run an empty query", async () => {
    renderPage();
    expect(screen.getByRole("button", { name: /^run$/i })).toBeDisabled();
  });

  it("runs an example with one click", async () => {
    post.mockResolvedValue({ data: result() });
    renderPage();

    await userEvent.click(screen.getByRole("button", { name: "severity:CRITICAL" }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/hunts/execute", { query: "severity:CRITICAL" }),
    );
  });

  it("saves a query for reuse", async () => {
    post.mockResolvedValue({ data: { id: 1 } });
    renderPage();

    await userEvent.type(screen.getByLabelText(/hunt query/i), "severity:HIGH");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/name/i), "High severity");
    await userEvent.click(within(dialog).getByRole("button", { name: /save hunt/i }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/hunts", {
        name: "High severity",
        query: "severity:HIGH",
        is_saved: true,
      }),
    );
  });

  it("re-runs a saved hunt", async () => {
    get.mockResolvedValue({
      data: [{ id: 3, name: "Okta criticals", query: "source:okta", description: null, is_saved: true }],
    });
    post.mockResolvedValue({ data: result() });
    renderPage();

    // Two "Run" buttons exist: the console's and the saved row's. Scope to the
    // row so this tests the saved-hunt path rather than the console input.
    const rowEl = (await screen.findByText("Okta criticals")).closest("div")!
      .parentElement!;
    await userEvent.click(within(rowEl).getByRole("button", { name: /^run$/i }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/hunts/execute", { query: "source:okta" }),
    );
  });

  it("reports a failure to load saved hunts", async () => {
    get.mockRejectedValue({ response: { data: { detail: "backend down" } } });
    renderPage();
    expect(await screen.findByText("backend down")).toBeInTheDocument();
  });
});
