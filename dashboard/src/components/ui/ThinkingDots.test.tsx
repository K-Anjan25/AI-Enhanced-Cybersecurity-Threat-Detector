import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThinkingDots, ThinkingIndicator } from "./ThinkingDots";

describe("ThinkingDots", () => {
  it("renders three dots, hidden from assistive tech", () => {
    const { container } = render(<ThinkingDots />);
    const dots = container.querySelectorAll("span > span");
    expect(dots).toHaveLength(3);
    // The dots are decoration; the meaning lives in the label.
    expect(container.querySelector("[aria-hidden='true']")).toBeInTheDocument();
  });

  it("staggers the dots so they read as a sequence, not a blink", () => {
    const { container } = render(<ThinkingDots />);
    const delays = Array.from(container.querySelectorAll("span > span")).map(
      (dot) => (dot as HTMLElement).style.animationDelay
    );
    expect(delays).toEqual(["0s", "0.16s", "0.32s"]);
  });

  it("announces the status once, with the label carrying the meaning", () => {
    render(<ThinkingIndicator label="NOCTRA is reasoning" />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("NOCTRA is reasoning");
    // The accessible name must not be "…" — the dots are aria-hidden.
    expect(status).not.toHaveTextContent("•••");
  });
});
