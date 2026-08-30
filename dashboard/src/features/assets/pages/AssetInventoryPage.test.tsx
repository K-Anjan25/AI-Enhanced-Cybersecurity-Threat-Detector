import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AssetInventoryPage from "./AssetInventoryPage";
import { ToastProvider } from "../../../components/ui/Toast";

const get = vi.fn();
const post = vi.fn();
vi.mock("../../../api/client", () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}));

/** "Add asset" labels both the header button and the modal submit. */
const submitButton = () =>
  within(screen.getByRole("dialog")).getByRole("button", { name: /^add asset$/i });

const renderPage = () =>
  render(
    <ToastProvider>
      <AssetInventoryPage />
    </ToastProvider>,
  );

const asset = (over: Record<string, unknown> = {}) => ({
  id: 1,
  name: "Primary file server",
  asset_type: "host",
  ip_address: "10.0.0.20",
  hostname: "fileserver01",
  criticality: 4,
  business_unit: "Finance",
  owner: "jo@acme.com",
  ...over,
});

describe("AssetInventoryPage", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it("lists assets the operator actually recorded", async () => {
    get.mockResolvedValue({ data: [asset()] });
    renderPage();

    expect(await screen.findByText("Primary file server")).toBeInTheDocument();
    expect(screen.getByText("fileserver01")).toBeInTheDocument();
    expect(screen.getByText("10.0.0.20")).toBeInTheDocument();
    expect(screen.getByText("Finance")).toBeInTheDocument();
  });

  it("promises an empty inventory rather than inventing crown jewels", async () => {
    get.mockResolvedValue({ data: [] });
    renderPage();

    expect(await screen.findByText("No assets recorded")).toBeInTheDocument();
    // The regression this guards: seed_assets() used to invent a "CEO Laptop".
    expect(screen.queryByText(/CEO Laptop/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Domain Controller/i)).not.toBeInTheDocument();
  });

  it("creates an asset and refreshes the list", async () => {
    get.mockResolvedValueOnce({ data: [] });
    post.mockResolvedValue({ data: asset() });
    get.mockResolvedValueOnce({ data: [asset()] });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /add your first asset/i }));
    await userEvent.type(screen.getByPlaceholderText("Primary file server"), "DB server");
    await userEvent.type(screen.getByPlaceholderText("fileserver01"), "db01");
    await userEvent.click(submitButton());

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [path, body] = post.mock.calls[0];
    expect(path).toBe("/risk-based/assets");
    expect(body).toMatchObject({ name: "DB server", hostname: "db01" });
    // List is re-fetched so the new row appears.
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it("will not submit an asset with no name", async () => {
    get.mockResolvedValue({ data: [] });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /add your first asset/i }));
    await userEvent.click(submitButton());

    expect(post).not.toHaveBeenCalled();
  });

  it("keeps the form open and reports the error when saving fails", async () => {
    get.mockResolvedValue({ data: [] });
    post.mockRejectedValue({ response: { data: { detail: "duplicate hostname" } } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /add your first asset/i }));
    await userEvent.type(screen.getByPlaceholderText("Primary file server"), "DB server");
    await userEvent.click(submitButton());

    expect(await screen.findByText("duplicate hostname")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Primary file server")).toBeInTheDocument();
  });

  it("surfaces a load failure", async () => {
    get.mockRejectedValue({ response: { data: { detail: "backend down" } } });
    renderPage();
    expect(await screen.findByText("backend down")).toBeInTheDocument();
  });
});
