import { describe, it, expect, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AttackSurfacePage from "./AttackSurfacePage";
import { ToastProvider } from "../../../components/ui/Toast";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../../api/client", () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}));

const renderPage = () =>
  render(
    <ToastProvider>
      <AttackSurfacePage />
    </ToastProvider>,
  );

const exposure = (over: Record<string, unknown> = {}) => ({
  id: 1,
  name: "vpn.acme.com",
  ip_address: "203.0.113.9",
  port: 443,
  service: "https",
  exposure_type: "published_hostname",
  severity: "LOW",
  description: "Published in certificate transparency. Reachability NOT checked.",
  evidence: { source: "certificate_transparency", port_scanned: false },
  status: "open",
  first_seen_at: "2026-02-19T14:26:03Z",
  last_seen_at: "2026-02-19T14:26:03Z",
  ...over,
});

const summary = (over: Record<string, unknown> = {}) => ({
  total_exposures: 3,
  open_exposures: 1,
  high: 0,
  critical: 0,
  expired_certs: 0,
  ...over,
});

/** The list and the summary are separate calls. */
const mockLoad = (list: unknown, totals: unknown = summary()) => {
  get.mockImplementation((path: string) =>
    path.includes("summary")
      ? Promise.resolve({ data: totals })
      : Promise.resolve({ data: list }),
  );
};

describe("AttackSurfacePage", () => {
  beforeEach(() => {
    cleanup();
    get.mockReset();
    post.mockReset();
  });

  it("lists what is exposed, with its evidence", async () => {
    mockLoad([exposure()]);
    renderPage();

    expect(await screen.findByText("vpn.acme.com")).toBeInTheDocument();
    expect(screen.getByText(":443")).toBeInTheDocument();
    expect(screen.getByText("Published hostname")).toBeInTheDocument();
    expect(screen.getByText(/Reachability NOT checked/)).toBeInTheDocument();
    expect(screen.getByText("Evidence")).toBeInTheDocument();
  });

  it("explains that open records drive attack paths", async () => {
    mockLoad([exposure()]);
    renderPage();

    expect(
      await screen.findByText(/used as a starting point when working out how an/),
    ).toBeInTheDocument();
  });

  it("warns that dismissing withdraws the attack paths built on it", async () => {
    mockLoad([exposure()]);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /not a finding/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/stop being\s+treated as a way in/)).toBeInTheDocument();
    expect(within(dialog).getByText(/will be\s+withdrawn/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("dismisses an exposure with the operator's reason", async () => {
    mockLoad([exposure()]);
    post.mockResolvedValue({ data: exposure({ status: "ignored" }) });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /not a finding/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/reason/i), "DNS no longer resolves");
    await userEvent.click(within(dialog).getByRole("button", { name: /dismiss exposure/i }));

    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][0]).toBe("/exposure/1/status");
    expect(post.mock.calls[0][1]).toMatchObject({
      status: "ignored",
      note: "DNS no longer resolves",
    });
  });

  it("marks an exposure fixed without claiming it is gone forever", async () => {
    mockLoad([exposure()]);
    post.mockResolvedValue({ data: exposure({ status: "fixed" }) });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /fixed/i }));

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/will reappear if discovery finds it\s+again/),
    ).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: /mark fixed/i }));
    await waitFor(() =>
      expect(post.mock.calls[0][1]).toMatchObject({ status: "fixed" }),
    );
  });

  it("surfaces a refusal rather than implying the change landed", async () => {
    mockLoad([exposure()]);
    post.mockRejectedValue({ response: { data: { detail: "Exposure not found" } } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /not a finding/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /dismiss exposure/i }));

    expect(await screen.findByText("Exposure not found")).toBeInTheDocument();
  });

  it("shows counts of what is open", async () => {
    mockLoad([exposure({ severity: "CRITICAL" })], summary({ open_exposures: 4, critical: 2 }));
    renderPage();

    await screen.findByText("vpn.acme.com");
    const tile = (label: string) => screen.getByText(label).parentElement!.parentElement!;
    expect(tile("Open")).toHaveTextContent("4");
    expect(tile("Critical")).toHaveTextContent("2");
  });

  it("says nothing is exposed rather than looking broken", async () => {
    mockLoad([], summary({ open_exposures: 0, total_exposures: 0 }));
    renderPage();

    expect(await screen.findByText("Nothing exposed")).toBeInTheDocument();
    expect(screen.getByText(/certificate transparency logs/)).toBeInTheDocument();
  });

  it("distinguishes an unreachable list from an empty one", async () => {
    get.mockRejectedValue({ response: { data: { detail: "backend down" } } });
    renderPage();

    expect(await screen.findByText("Attack surface unavailable")).toBeInTheDocument();
    expect(screen.getByText(/failure, not an empty attack surface/)).toBeInTheDocument();
  });
});
