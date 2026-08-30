import { describe, it, expect, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import ApprovalsPage from "./ApprovalsPage";
import { ToastProvider } from "../../../components/ui/Toast";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../../api/client", () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}));

const CURRENT_USER = 7;

const renderPage = (userId: number | null = CURRENT_USER) => {
  const store = configureStore({
    reducer: {
      user: () => ({
        user: userId === null ? null : { userId: String(userId) },
        isLogedIn: true,
        loading: false,
        error: null,
      }),
    },
  });
  return render(
    <Provider store={store}>
      <ToastProvider>
        <ApprovalsPage />
      </ToastProvider>
    </Provider>,
  );
};

const instance = (over: Record<string, unknown> = {}) => ({
  id: 1,
  workflow_id: 1,
  workflow_name: "Critical Action - SOC Lead Approval",
  action_type: "isolate_host",
  target: "fileserver01",
  case_id: 12,
  current_step: 1,
  total_steps: 1,
  status: "pending",
  requested_by_user_id: 99,
  approvals: [],
  created_at: new Date(Date.now() - 45 * 60_000).toISOString(),
  decided_at: null,
  ...over,
});

describe("ApprovalsPage", () => {
  beforeEach(() => {
    cleanup();
    get.mockReset();
    post.mockReset();
  });

  it("shows what is waiting and what it would do", async () => {
    get.mockResolvedValue({ data: [instance()] });
    renderPage();

    expect(await screen.findByText("Isolate host")).toBeInTheDocument();
    expect(screen.getByText("fileserver01")).toBeInTheDocument();
    expect(screen.getByText(/Critical Action - SOC Lead Approval/)).toBeInTheDocument();
    expect(screen.getByText(/case #12/)).toBeInTheDocument();
  });

  it("shows how long a request has been blocked", async () => {
    get.mockResolvedValue({ data: [instance()] });
    renderPage();
    expect(await screen.findByText(/waiting 45 min/)).toBeInTheDocument();
  });

  it("shows progress through a multi-stage workflow", async () => {
    get.mockResolvedValue({
      data: [instance({ current_step: 2, total_steps: 3 })],
    });
    renderPage();
    expect(await screen.findByText(/stage 2 of 3/)).toBeInTheDocument();
  });

  it("hides the decision buttons on a request you raised", async () => {
    get.mockResolvedValue({
      data: [instance({ requested_by_user_id: CURRENT_USER })],
    });
    renderPage();

    await screen.findByText("Isolate host");
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    expect(
      screen.getByText(/You raised this, so someone else has to decide it/),
    ).toBeInTheDocument();
  });

  it("counts your own requests separately so you know they are stuck", async () => {
    get.mockResolvedValue({
      data: [
        instance({ id: 1, requested_by_user_id: CURRENT_USER }),
        instance({ id: 2, requested_by_user_id: 99 }),
      ],
    });
    renderPage();

    expect(await screen.findByText(/raised by\s+you and needs someone else/)).toBeInTheDocument();
  });

  it("explains what approving will do before recording it", async () => {
    get.mockResolvedValue({ data: [instance()] });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /^approve$/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/will run against/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("says a later stage is still required when one remains", async () => {
    get.mockResolvedValue({
      data: [instance({ current_step: 1, total_steps: 2 })],
    });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /^approve$/i }));

    expect(
      await screen.findByText(/once the remaining stage is approved/),
    ).toBeInTheDocument();
  });

  it("records an approval with the comment", async () => {
    get.mockResolvedValue({ data: [instance()] });
    post.mockResolvedValue({ data: { id: 1, status: "approved" } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /^approve$/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/comment/i), "Confirmed with owner");
    await userEvent.click(within(dialog).getByRole("button", { name: /^approve$/i }));

    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][0]).toBe("/approval-workflows/instances/1/decide");
    expect(post.mock.calls[0][1]).toMatchObject({
      decision: "approved",
      comment: "Confirmed with owner",
    });
  });

  it("records a rejection", async () => {
    get.mockResolvedValue({ data: [instance()] });
    post.mockResolvedValue({ data: { id: 1, status: "rejected" } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /^reject$/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /^reject$/i }));

    await waitFor(() =>
      expect(post.mock.calls[0][1]).toMatchObject({ decision: "rejected" }),
    );
  });

  it("surfaces a server-side refusal rather than implying it worked", async () => {
    get.mockResolvedValue({ data: [instance()] });
    post.mockRejectedValue({
      response: {
        data: { detail: "You have already decided this request." },
      },
    });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /^approve$/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /^approve$/i }));

    expect(await screen.findByText(/already decided this request/)).toBeInTheDocument();
  });

  it("offers no buttons on a settled request", async () => {
    get.mockResolvedValue({ data: [instance({ status: "approved" })] });
    renderPage();

    await screen.findByText("Isolate host");
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^reject$/i })).not.toBeInTheDocument();
  });

  it("distinguishes an empty queue from an unreachable one", async () => {
    get.mockResolvedValue({ data: [] });
    renderPage();
    expect(await screen.findByText("Nothing waiting for approval")).toBeInTheDocument();

    cleanup();
    get.mockReset();
    get.mockRejectedValue({ response: { data: { detail: "backend down" } } });
    renderPage();

    expect(await screen.findByText("Approval queue unavailable")).toBeInTheDocument();
    expect(screen.getByText(/failure, not an empty queue/)).toBeInTheDocument();
  });
});
