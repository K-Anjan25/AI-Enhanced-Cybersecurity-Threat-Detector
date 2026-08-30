import { describe, it, expect, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import GdprRequestsPage from "./GdprRequestsPage";
import { ToastProvider } from "../../../components/ui/Toast";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../../api/client", () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}));

/** "Log request" labels both the header action and the modal submit. */
const submitLogRequest = () =>
  within(screen.getByRole("dialog")).getByRole("button", { name: /^log request$/i });

const renderPage = () =>
  render(
    <ToastProvider>
      <GdprRequestsPage />
    </ToastProvider>,
  );

const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

const request = (over: Record<string, unknown> = {}) => ({
  id: 1,
  target_email: "person@example.com",
  reason: "Emailed the DPO",
  status: "pending",
  created_at: daysAgo(3),
  completed_at: null,
  ...over,
});

describe("GdprRequestsPage", () => {
  beforeEach(() => {
    cleanup();
    get.mockReset();
    post.mockReset();
  });

  it("lists requests with their subject and status", async () => {
    get.mockResolvedValue({ data: [request()] });
    renderPage();

    expect(await screen.findByText("person@example.com")).toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(screen.getByText("Emailed the DPO")).toBeInTheDocument();
  });

  it("shows how long a request has been waiting", async () => {
    get.mockResolvedValue({ data: [request({ created_at: daysAgo(5) })] });
    renderPage();
    expect(await screen.findByText(/open 5 days/)).toBeInTheDocument();
  });

  it("warns when a request passes the one-month deadline", async () => {
    get.mockResolvedValue({ data: [request({ created_at: daysAgo(45) })] });
    renderPage();

    expect(
      await screen.findByText(/has been\s+open longer than 30 days/),
    ).toBeInTheDocument();
    expect(screen.getByText(/respond within one month/)).toBeInTheDocument();
  });

  it("does not warn when everything is inside the deadline", async () => {
    get.mockResolvedValue({ data: [request({ created_at: daysAgo(2) })] });
    renderPage();
    await screen.findByText("person@example.com");
    expect(screen.queryByText(/respond within one month/)).not.toBeInTheDocument();
  });

  it("spells out that approving is irreversible before doing it", async () => {
    get.mockResolvedValue({ data: [request()] });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /approve erasure/i }));

    // Scope to the dialog: other confirmations on the page share this wording.
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Approve this erasure?")).toBeInTheDocument();
    expect(within(dialog).getByText(/anonymised in place/)).toBeInTheDocument();
    expect(within(dialog).getByText(/cannot be undone/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("approves only after confirmation", async () => {
    get.mockResolvedValue({ data: [request()] });
    post.mockResolvedValue({ data: { id: 1, status: "approved" } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /approve erasure/i }));
    await userEvent.click(screen.getByRole("button", { name: /anonymise account/i }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/data-lifecycle/gdpr/1/approve"),
    );
  });

  it("rejects a request without deleting anything", async () => {
    get.mockResolvedValue({ data: [request()] });
    post.mockResolvedValue({ data: { id: 1, status: "rejected" } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /^reject$/i }));
    expect(await screen.findByText(/no data will be deleted/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /reject request/i }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/data-lifecycle/gdpr/1/reject"),
    );
  });

  it("offers no decision buttons on a settled request", async () => {
    get.mockResolvedValue({ data: [request({ status: "completed" })] });
    renderPage();

    await screen.findByText("person@example.com");
    expect(screen.queryByRole("button", { name: /approve erasure/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^reject$/i })).not.toBeInTheDocument();
  });

  it("surfaces a backend refusal rather than implying it worked", async () => {
    get.mockResolvedValue({ data: [request()] });
    post.mockRejectedValue({
      response: { data: { detail: "Request is already approved; erasure cannot be reversed." } },
    });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /approve erasure/i }));
    await userEvent.click(screen.getByRole("button", { name: /anonymise account/i }));

    expect(await screen.findByText(/erasure cannot be reversed/)).toBeInTheDocument();
  });

  it("logs a new request", async () => {
    get.mockResolvedValue({ data: [] });
    post.mockResolvedValue({ data: { id: 2 } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /log request/i }));
    await userEvent.type(screen.getByLabelText(/subject email/i), "new@example.com");
    await userEvent.click(submitLogRequest());

    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][0]).toBe("/data-lifecycle/gdpr");
    expect(post.mock.calls[0][1]).toMatchObject({ target_email: "new@example.com" });
  });

  it("will not log a request with no subject", async () => {
    get.mockResolvedValue({ data: [] });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /log request/i }));
    expect(submitLogRequest()).toBeDisabled();
  });

  it("distinguishes an empty queue from an unreachable one", async () => {
    get.mockResolvedValue({ data: [] });
    renderPage();
    expect(await screen.findByText("No erasure requests")).toBeInTheDocument();

    cleanup();
    get.mockReset();
    get.mockRejectedValue({ response: { data: { detail: "backend down" } } });
    renderPage();

    expect(await screen.findByText("Erasure queue unavailable")).toBeInTheDocument();
    expect(screen.getByText(/failure, not an empty queue/)).toBeInTheDocument();
  });
});
