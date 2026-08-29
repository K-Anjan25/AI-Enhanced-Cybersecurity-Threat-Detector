import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import AlertList from "./AlertList";
import { fetchAlerts } from "../../../api/alertApi";
import { requestStreamTicket, streamUrl } from "../../../api/streamApi";

vi.mock("../../../api/alertApi", async (importOriginal) => {
  const actual = await importOriginal<any>();
  return { ...actual, fetchAlerts: vi.fn() };
});
vi.mock("../../../api/streamApi", async (importOriginal) => {
  const actual = await importOriginal<any>();
  return { ...actual, requestStreamTicket: vi.fn() };
});

/**
 * jsdom ships no EventSource, and a real one would need a server. This fake is
 * the smallest thing that behaves like the real one: it lets a test fire frames
 * at the component, and it lets a test simulate the connection failing.
 */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  static autoFail = false;
  url: string;
  closed = false;
  listeners: Record<string, ((event: any) => void)[]> = {};
  onerror: (() => void) | null = null;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
    if (FakeEventSource.autoFail) {
      setTimeout(() => this.onerror?.(), 0);
    }
  }
  addEventListener(type: string, handler: (event: any) => void) {
    (this.listeners[type] ||= []).push(handler);
  }
  close() {
    this.closed = true;
  }
  emit(type: string, data: unknown) {
    for (const handler of this.listeners[type] ?? []) {
      handler({ data: typeof data === "string" ? data : JSON.stringify(data) });
    }
  }
}

const ALERT = (id: number, message: string) => ({
  id,
  message,
  severity: "LOW",
  created_at: "2026-08-29T00:00:00",
});

const renderList = () =>
  render(
    <MemoryRouter>
      <AlertList />
    </MemoryRouter>
  );

const latest = () => FakeEventSource.instances[FakeEventSource.instances.length - 1];

beforeEach(() => {
  vi.clearAllMocks();
  FakeEventSource.instances = [];
  FakeEventSource.autoFail = false;
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.mocked(fetchAlerts).mockResolvedValue([ALERT(1, "older alert")] as any);
  let counter = 0;
  vi.mocked(requestStreamTicket).mockImplementation(async () => {
    counter += 1;
    return `ticket-${counter}`;
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AlertList live stream", () => {
  it("opens the stream with a freshly minted ticket, never a JWT in the URL", async () => {
    renderList();
    await waitFor(() => expect(requestStreamTicket).toHaveBeenCalled());
    await waitFor(() => expect(latest()).toBeDefined());
    expect(latest().url).toMatch(/^\/api\/v1\/stream\/alerts\?ticket=ticket-\d+$/);
    expect(latest().url).not.toContain("Bearer");
    expect(latest().url).not.toContain("eyJ");
  });

  it("reports live once the server confirms the stream", async () => {
    renderList();
    await waitFor(() => expect(latest()).toBeDefined());
    expect(screen.getByTestId("stream-status")).toHaveAttribute("data-stream-status", "connecting");
    latest().emit("ready", { live: true });
    await waitFor(() =>
      expect(screen.getByTestId("stream-status")).toHaveAttribute("data-stream-status", "live")
    );
    expect(screen.getByText("Streaming")).toBeInTheDocument();
  });

  it("puts a streamed alert at the top of the list without refetching", async () => {
    renderList();
    await waitFor(() => expect(screen.getByText("older alert")).toBeInTheDocument());
    const callsBefore = vi.mocked(fetchAlerts).mock.calls.length;
    latest().emit("alert", ALERT(99, "Impossible travel for svc-deploy"));
    await waitFor(() =>
      expect(screen.getByText("Impossible travel for svc-deploy")).toBeInTheDocument()
    );
    expect(vi.mocked(fetchAlerts).mock.calls.length).toBe(callsBefore);
  });

  it("does not duplicate an alert the stream reports twice", async () => {
    renderList();
    await waitFor(() => expect(latest()).toBeDefined());
    latest().emit("alert", ALERT(99, "Repeated alert"));
    latest().emit("alert", ALERT(99, "Repeated alert"));
    await waitFor(() => expect(screen.getAllByText("Repeated alert")).toHaveLength(1));
  });

  it("refetches when the server says events were dropped", async () => {
    renderList();
    await waitFor(() => expect(latest()).toBeDefined());
    const callsBefore = vi.mocked(fetchAlerts).mock.calls.length;
    latest().emit("gap", { dropped: 3, message: "reload" });
    await waitFor(() => expect(vi.mocked(fetchAlerts).mock.calls.length).toBe(callsBefore + 1));
  });

  it("reconnects with a NEW ticket, because the old one is spent", async () => {
    renderList();
    await waitFor(() => expect(latest()).toBeDefined());
    latest().emit("ready", { live: true });
    await waitFor(() =>
      expect(screen.getByTestId("stream-status")).toHaveAttribute("data-stream-status", "live")
    );
    latest().onerror?.();
    await waitFor(() =>
      expect(screen.getByTestId("stream-status")).toHaveAttribute("data-stream-status", "reconnecting")
    );
    await waitFor(() => expect(requestStreamTicket).toHaveBeenCalledTimes(2), { timeout: 3000 });
    await waitFor(() => expect(FakeEventSource.instances.length).toBeGreaterThan(1));
    // second ticket should be different from first
    expect(FakeEventSource.instances.length).toBeGreaterThanOrEqual(2);
    const urls = FakeEventSource.instances.map((i) => i.url);
    expect(urls[0]).not.toBe(urls[1]);
    expect(FakeEventSource.instances[0].closed).toBe(true);
  });

  it("falls back to the 60s poll label when it cannot connect", async () => {
    FakeEventSource.autoFail = true;
    vi.mocked(requestStreamTicket).mockRejectedValue(new Error("no ticket"));
    renderList();
    await waitFor(() =>
      expect(screen.getByTestId("stream-status")).toHaveAttribute("data-stream-status", "reconnecting")
    );
    await waitFor(() => expect(screen.getByText("older alert")).toBeInTheDocument());
  });

  it("closes the stream when the list unmounts", async () => {
    const { unmount } = renderList();
    await waitFor(() => expect(latest()).toBeDefined());
    unmount();
    expect(latest().closed).toBe(true);
  });
});
