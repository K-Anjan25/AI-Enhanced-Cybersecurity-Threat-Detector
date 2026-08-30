import { describe, it, expect, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DataRetentionPage from "./DataRetentionPage";
import { ToastProvider } from "../../../components/ui/Toast";

const get = vi.fn();
const post = vi.fn();
const del = vi.fn();
vi.mock("../../../api/client", () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
    delete: (...a: unknown[]) => del(...a),
  },
}));

const renderPage = () =>
  render(
    <ToastProvider>
      <DataRetentionPage />
    </ToastProvider>,
  );

const policy = (over: Record<string, unknown> = {}) => ({
  id: 1,
  data_type: "alerts",
  retention_days: 90,
  archive_after_days: 60,
  delete_after_days: 90,
  is_active: true,
  ...over,
});

/** Policies resolve first, legal holds second. */
const mockLoad = (policies: unknown, holds: unknown = []) => {
  get.mockImplementation((path: string) =>
    path.includes("legal-holds")
      ? Promise.resolve({ data: holds })
      : Promise.resolve({ data: policies }),
  );
};

describe("DataRetentionPage", () => {
  beforeEach(() => {
    cleanup();
    get.mockReset();
    post.mockReset();
    del.mockReset();
  });

  it("shows each policy's retention thresholds", async () => {
    mockLoad([policy(), policy({ id: 2, data_type: "cases", retention_days: 365 })]);
    renderPage();

    // Assert per-row so the alerts and cases thresholds cannot be confused.
    // Each policy renders as label + thresholds inside a shared row div.
    const row = (dataType: string) =>
      screen.getByText(dataType).parentElement!.parentElement!;
    expect(await screen.findByText("alerts")).toBeInTheDocument();
    expect(row("alerts")).toHaveTextContent("keep 90d");
    expect(row("alerts")).toHaveTextContent("archive 60d");
    expect(row("cases")).toHaveTextContent("keep 365d");
  });

  it("explains the posture-score consequence when no policy exists", async () => {
    mockLoad([]);
    renderPage();
    expect(await screen.findByText("No retention policies")).toBeInTheDocument();
  });

  it("states plainly when nothing is under legal hold", async () => {
    mockLoad([policy()], []);
    renderPage();
    expect(
      await screen.findByText(/No active holds — retention runs without exception\./),
    ).toBeInTheDocument();
  });

  it("lists active legal holds so operators know retention is being skipped", async () => {
    mockLoad([policy()], [{ id: 7, name: "Litigation 2026", reason: "pending case", is_active: true }]);
    renderPage();
    expect(await screen.findByText("Litigation 2026")).toBeInTheDocument();
  });

  it("renders the hold fields the API actually returns", async () => {
    // Regression: the page declared `reason`/`data_type`, which the endpoint
    // never sends, so every hold rendered with a blank detail line.
    mockLoad([policy()], [
      {
        id: 7,
        name: "Litigation 2026",
        description: "Preserve mailbox exports",
        case_ids: [11, 12],
        is_active: true,
      },
    ]);
    renderPage();

    expect(await screen.findByText("Litigation 2026")).toBeInTheDocument();
    expect(screen.getByText("Preserve mailbox exports")).toBeInTheDocument();
    expect(screen.getByText(/2 cases/)).toBeInTheDocument();
  });

  it("creates a legal hold and reloads", async () => {
    mockLoad([policy()], []);
    post.mockResolvedValue({ data: { id: 1 } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /new hold/i }));
    await userEvent.type(screen.getByLabelText(/name/i), "Acme litigation");
    await userEvent.type(screen.getByLabelText(/reason/i), "Preserve everything");
    await userEvent.click(screen.getByRole("button", { name: /create hold/i }));

    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][0]).toBe("/data-lifecycle/legal-holds");
    expect(post.mock.calls[0][1]).toMatchObject({
      name: "Acme litigation",
      description: "Preserve everything",
    });
  });

  it("will not create a hold with no name", async () => {
    mockLoad([policy()], []);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /new hold/i }));
    expect(screen.getByRole("button", { name: /create hold/i })).toBeDisabled();
    expect(post).not.toHaveBeenCalled();
  });

  it("warns what releasing a hold exposes before doing it", async () => {
    mockLoad([policy()], [{ id: 7, name: "Litigation 2026", is_active: true }]);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /release/i }));

    expect(await screen.findByText("Release this legal hold?")).toBeInTheDocument();
    expect(
      screen.getByText(/may archive or delete records this hold was preserving/),
    ).toBeInTheDocument();
    expect(del).not.toHaveBeenCalled();
  });

  it("releases a hold once confirmed", async () => {
    mockLoad([policy()], [{ id: 7, name: "Litigation 2026", is_active: true }]);
    del.mockResolvedValue({ data: { status: "released" } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /^release$/i }));
    await userEvent.click(screen.getByRole("button", { name: /release hold/i }));

    await waitFor(() =>
      expect(del).toHaveBeenCalledWith("/data-lifecycle/legal-holds/7"),
    );
  });

  it("reports a failed release instead of implying the hold is gone", async () => {
    mockLoad([policy()], [{ id: 7, name: "Litigation 2026", is_active: true }]);
    del.mockRejectedValue({ response: { data: { detail: "hold is locked" } } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /^release$/i }));
    await userEvent.click(screen.getByRole("button", { name: /release hold/i }));

    expect(await screen.findByText("hold is locked")).toBeInTheDocument();
  });

  it("requires confirmation before running retention, and warns it is irreversible", async () => {
    mockLoad([policy()]);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /run retention now/i }));

    expect(await screen.findByText("Run retention now?")).toBeInTheDocument();
    expect(screen.getByText(/active legal hold is skipped/i)).toBeInTheDocument();
    expect(
      screen.getByText(/report what is eligible without moving or deleting anything/i),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("does not run retention when the operator cancels", async () => {
    mockLoad([policy()]);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /run retention now/i }));
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));

    await waitFor(() => expect(screen.queryByText("Run retention now?")).not.toBeInTheDocument());
    expect(post).not.toHaveBeenCalled();
  });

  it("runs the automation once confirmed and reloads", async () => {
    mockLoad([policy()]);
    post.mockResolvedValue({ data: { archived: 12 } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /run retention now/i }));
    await userEvent.click(screen.getByRole("button", { name: /^run retention$/i }));

    await waitFor(() => expect(post).toHaveBeenCalledWith("/data-lifecycle/automation/run"));
  });

  it("reports a failed retention run instead of implying success", async () => {
    mockLoad([policy()]);
    post.mockRejectedValue({ response: { data: { detail: "archive target unavailable" } } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /run retention now/i }));
    await userEvent.click(screen.getByRole("button", { name: /^run retention$/i }));

    expect(await screen.findByText("archive target unavailable")).toBeInTheDocument();
  });
});
