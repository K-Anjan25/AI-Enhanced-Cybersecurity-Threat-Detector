/**
 * Test environment setup — jsdom lacks the browser APIs the dashboard relies
 * on. Everything here is a stub of something the browser provides, so a test
 * failing for a *real* reason never looks like an environment problem.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

// Recharts measures its container; jsdom reports every element as 0x0.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", ResizeObserverStub);

// framer-motion + LandingHero both read this; default to "no preference" and
// let individual tests override it.
if (!window.matchMedia) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  );
}

// jsdom does not implement scrollIntoView.
Element.prototype.scrollIntoView = vi.fn();
