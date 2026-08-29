import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { QueryClient, QueryClientProvider } from "react-query";

import CommandMenu, { COMMAND_MENU_EVENT } from "./CommandMenu";
import AnalystApi from "../api/analystApi";

vi.mock("../api/analystApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/analystApi")>();
  return {
    ...actual,
    default: {
      ...actual.default,
      fetchFeed: vi.fn(),
      simulate: vi.fn(),
    },
  };
});

const mocked = vi.mocked(AnalystApi);

const renderMenu = () => {
  const store = configureStore({ reducer: { user: () => ({}) } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <Provider store={store}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <CommandMenu />
        </MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  mocked.fetchFeed.mockResolvedValue({ data: [], total: 0, page: 1, limit: 100 } as never);
  mocked.simulate.mockResolvedValue({ id: 1 } as never);
});

describe("CommandMenu", () => {
  it("opens on Ctrl+K and shows navigate + simulate actions", async () => {
    renderMenu();

    // Dispatch the open event (Navbar button uses it)
    window.dispatchEvent(new Event(COMMAND_MENU_EVENT));

    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(screen.getByText(/Home/)).toBeInTheDocument();
    expect(screen.getByText(/Simulate: Credential leak/)).toBeInTheDocument();
    expect(screen.getByText(/Simulate: Insider threat/)).toBeInTheDocument();
    expect(screen.getByText(/Simulate: Ransomware activity/)).toBeInTheDocument();
  });

  it("filters commands by query", async () => {
    renderMenu();
    window.dispatchEvent(new Event(COMMAND_MENU_EVENT));
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());

    const user = userEvent.setup();
    const input = screen.getByRole("combobox");
    await user.type(input, "ransomware");

    await waitFor(() => {
      expect(screen.getByText(/Ransomware activity/)).toBeInTheDocument();
      expect(screen.queryByText(/Phishing outbreak/)).not.toBeInTheDocument();
    });
  });

  it("closes on Escape", async () => {
    renderMenu();
    window.dispatchEvent(new Event(COMMAND_MENU_EVENT));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    const user = userEvent.setup();
    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
