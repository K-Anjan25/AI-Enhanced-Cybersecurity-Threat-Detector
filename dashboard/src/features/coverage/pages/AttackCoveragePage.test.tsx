import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AttackCoveragePage from "./AttackCoveragePage";
import { ToastProvider } from "../../../components/ui/Toast";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../../api/client", () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}));

/** Toast text lands in the DOM, so assert on it there rather than mocking. */
const renderPage = () =>
  render(
    <ToastProvider>
      <AttackCoveragePage />
    </ToastProvider>,
  );

const row = (over: Record<string, unknown> = {}) => ({
  id: 1,
  tactic: "Initial Access",
  technique_id: "T1190",
  technique_name: "Exploit Public-Facing Application",
  has_rule: true,
  has_hunt: false,
  has_playbook: false,
  has_exercise: false,
  detection_count: 3,
  coverage_score: 25,
  gap_reason: null,
  recommendation: null,
  ...over,
});

describe("AttackCoveragePage", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it("summarises real coverage instead of a raw payload", async () => {
    get.mockResolvedValue({
      data: [
        row(),
        row({ id: 2, technique_id: "T1078", coverage_score: 0, has_rule: false, detection_count: 0 }),
      ],
    });
    renderPage();

    expect(await screen.findByText("T1190")).toBeInTheDocument();
    // 1 of 2 techniques has any coverage. The uncovered one also appears in
    // the gaps panel, so scope the assertions to the summary tiles.
    const tile = (label: string) =>
      screen.getByText(label).parentElement!.parentElement!;
    expect(tile("With some coverage")).toHaveTextContent("50%");
    expect(tile("Techniques tracked")).toHaveTextContent("2");
    expect(tile("Uncovered")).toHaveTextContent("1");
    expect(screen.getAllByText("Exploit Public-Facing Application").length).toBeGreaterThan(0);
  });

  it("groups techniques under their tactic", async () => {
    get.mockResolvedValue({
      data: [row(), row({ id: 2, tactic: "Persistence", technique_id: "T1136" })],
    });
    renderPage();

    expect(await screen.findByText("Initial Access")).toBeInTheDocument();
    expect(screen.getByText("Persistence")).toBeInTheDocument();
  });

  it("calls out uncovered techniques with their recommendation", async () => {
    get.mockResolvedValue({
      data: [row({ coverage_score: 0, recommendation: "Write a Sigma rule for T1190" })],
    });
    renderPage();

    expect(await screen.findByText("Biggest gaps")).toBeInTheDocument();
    expect(screen.getByText("Write a Sigma rule for T1190")).toBeInTheDocument();
  });

  it("hides the gaps panel when everything has coverage", async () => {
    get.mockResolvedValue({ data: [row({ coverage_score: 100 })] });
    renderPage();

    await screen.findByText("T1190");
    expect(screen.queryByText("Biggest gaps")).not.toBeInTheDocument();
  });

  it("shows an empty state rather than a fake score", async () => {
    get.mockResolvedValue({ data: [] });
    renderPage();
    expect(await screen.findByText("No coverage evaluated yet")).toBeInTheDocument();
  });

  it("re-evaluates on demand and reports the count", async () => {
    get.mockResolvedValue({ data: [row()] });
    post.mockResolvedValue({ data: [row(), row({ id: 2, technique_id: "T1078" })] });
    renderPage();

    await screen.findByText("T1190");
    await userEvent.click(screen.getByRole("button", { name: /re-evaluate/i }));

    await waitFor(() => expect(post).toHaveBeenCalledWith("/attack-coverage/evaluate"));
    expect(await screen.findByText("T1078")).toBeInTheDocument();
    expect(await screen.findByText(/2 technique/)).toBeInTheDocument();
  });

  it("surfaces a load failure to the operator", async () => {
    get.mockRejectedValue(new Error("boom"));
    renderPage();
    // getApiError surfaces the underlying message.
    expect(await screen.findByText("boom")).toBeInTheDocument();
  });

  it("tolerates a non-array error payload from the endpoint", async () => {
    get.mockResolvedValue({ data: { status: "error", detail: "nope" } });
    renderPage();
    expect(await screen.findByText("No coverage evaluated yet")).toBeInTheDocument();
  });
});
