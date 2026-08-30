import { describe, it, expect, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResponseTimesPage from "./ResponseTimesPage";
import { ToastProvider } from "../../../components/ui/Toast";

const get = vi.fn();
vi.mock("../../../api/client", () => ({ default: { get: (...a: unknown[]) => get(...a) } }));

const renderPage = () =>
  render(
    <ToastProvider>
      <ResponseTimesPage />
    </ToastProvider>,
  );

const metric = (over: Record<string, unknown> = {}) => ({
  metric: "time_to_triage",
  measures: "alert ingested → case raised",
  sample_size: 12,
  median_minutes: 9,
  p90_minutes: 20,
  fastest_minutes: 2,
  slowest_minutes: 50,
  reliable: true,
  reason: null,
  caveat: "Starts at ingest, not at the moment of attack. This is not a true MTTD.",
  ...over,
});

const report = (over: Record<string, unknown> = {}) => ({
  window_days: 30,
  cases_in_window: 12,
  metrics: [metric()],
  open_backlog: { undecided_cases: 3, oldest_undecided_minutes: 480 },
  not_measured: [
    { metric: "cost_avoidance", reason: "depends on breach-cost assumptions" },
  ],
  ...over,
});

describe("ResponseTimesPage", () => {
  beforeEach(() => {
    // Unmount the previous page first: a fetch still in flight would otherwise
    // resolve against the freshly reset mock and surface as an unhandled
    // rejection attributed to whichever test runs next.
    cleanup();
    get.mockReset();
  });

  it("shows measured percentiles with the sample size behind them", async () => {
    get.mockResolvedValue({ data: report() });
    renderPage();

    expect(await screen.findByText("9 min")).toBeInTheDocument();
    expect(screen.getByText("20 min")).toBeInTheDocument();
    expect(screen.getByText("n=12")).toBeInTheDocument();
  });

  it("scales the unit so long durations stay readable", async () => {
    get.mockResolvedValue({
      data: report({ metrics: [metric({ median_minutes: 300, p90_minutes: 4320 })] }),
    });
    renderPage();

    expect(await screen.findByText("5.0 h")).toBeInTheDocument();
    expect(screen.getByText("3.0 d")).toBeInTheDocument();
  });

  it("carries the caveat that this is not a true MTTD", async () => {
    get.mockResolvedValue({ data: report() });
    renderPage();
    expect(await screen.findByText(/not a true MTTD/)).toBeInTheDocument();
  });

  it("warns when a metric rests on too small a sample", async () => {
    get.mockResolvedValue({
      data: report({
        metrics: [
          metric({ sample_size: 2, reliable: false, reason: "only 2 case(s) measured; 5 needed" }),
        ],
      }),
    });
    renderPage();
    expect(await screen.findByText(/only 2 case\(s\) measured; 5 needed/)).toBeInTheDocument();
  });

  it("says nothing was measured rather than showing zero", async () => {
    get.mockResolvedValue({
      data: report({
        metrics: [
          metric({
            median_minutes: null,
            p90_minutes: null,
            sample_size: 0,
            reliable: false,
            reason: "no cases in this window have both timestamps recorded",
          }),
        ],
      }),
    });
    renderPage();

    expect(await screen.findByText(/Nothing measured yet/)).toBeInTheDocument();
    expect(screen.queryByText("0 min")).not.toBeInTheDocument();
  });

  it("distinguishes a real zero from a failure", async () => {
    get.mockResolvedValue({ data: report({ cases_in_window: 0 }) });
    renderPage();
    expect(await screen.findByText("No cases in this window")).toBeInTheDocument();
    expect(screen.getByText(/real zero, not a failure/)).toBeInTheDocument();
  });

  it("lists what cannot be measured and why", async () => {
    get.mockResolvedValue({ data: report() });
    renderPage();

    expect(await screen.findByText(/Not measured \(1\)/)).toBeInTheDocument();
    expect(screen.getByText("Cost avoidance")).toBeInTheDocument();
    expect(screen.getByText(/depends on breach-cost assumptions/)).toBeInTheDocument();
    expect(screen.getByText(/would be a guess presented as a result/)).toBeInTheDocument();
  });

  it("refetches when the window changes", async () => {
    get.mockResolvedValue({ data: report() });
    renderPage();
    await screen.findByText("9 min");

    await userEvent.selectOptions(screen.getByLabelText(/window/i), "7");

    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith("/exec-risk/response-times?window_days=7"),
    );
  });

  it("reports a load failure instead of implying no activity", async () => {
    get.mockRejectedValue({ response: { data: { detail: "backend down" } } });
    renderPage();

    expect(await screen.findByText("Response times unavailable")).toBeInTheDocument();
    expect(screen.getByText(/failure, not an absence of activity/)).toBeInTheDocument();
  });
});
