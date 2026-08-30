import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import ModulePage from "./ModulePage";

/**
 * Jakob's Law: a nav item must land on what it names.
 *
 * These routes share a tabbed hub. Every one of them used to open the hub on
 * its first tab, so "Vulnerabilities" showed ZTNA and "Forensics" showed ITDR.
 */

vi.mock("../../../api/client", () => ({
  default: { get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn().mockResolvedValue({ data: {} }) },
}));
vi.mock("../../../api/advancedApi", () => ({
  advancedApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({ data: {} }) }),
}));

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<ModulePage />} />
      </Routes>
    </MemoryRouter>,
  );

/** The selected tab is the one with aria/visual active state — we assert on the heading. */
const activeHeading = () => screen.getByRole("heading", { level: 3 }).textContent?.toLowerCase();

describe("ModulePage tab routing", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([
    ["/vulns", "vuln"],
    ["/ztna", "ztna"],
    ["/hunting", "hunt"],
    ["/ai-agent", "agent"],
  ])("opens %s on its own tab", async (path, expected) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { level: 3 })).toBeInTheDocument();
    expect(activeHeading()).toBe(expected);
  });

  it.each([
    ["/cspm", "cspm"],
    ["/forensics", "forensics"],
    ["/sbom", "sbom"],
    ["/exec-risk", "exec"],
  ])("opens %s on its own tab", async (path, expected) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { level: 3 })).toBeInTheDocument();
    expect(activeHeading()).toBe(expected);
  });

  it("still resolves nested paths to the right tab", async () => {
    renderAt("/vulns/123");
    expect(await screen.findByRole("heading", { level: 3 })).toBeInTheDocument();
    expect(activeHeading()).toBe("vuln");
  });

  it("falls back for an unmapped module instead of blank-screening", () => {
    renderAt("/not-a-module");
    expect(screen.getByText(/view in Advanced Hub/i)).toBeInTheDocument();
  });
});
