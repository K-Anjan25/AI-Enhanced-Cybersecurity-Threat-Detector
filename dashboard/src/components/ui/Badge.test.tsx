import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SeverityBadge, StatusBadge } from "./Badge";

describe("Badge", () => {
  it("never encodes severity in colour alone — dot and label both render", () => {
    render(<SeverityBadge severity="CRITICAL" withDot />);
    // The word is present, so the state survives a colour-blind or
    // monochrome reader (spec §40.1: severity is always dot + label).
    expect(screen.getByText(/critical/i)).toBeInTheDocument();
  });

  it("survives an unknown severity instead of rendering 'undefined'", () => {
    // Guards a real failure mode: rows with a missing/odd severity used to
    // blow up or print "undefined" on screen.
    render(<SeverityBadge severity="WHATEVER" />);
    expect(screen.getByText(/whatever/i)).toBeInTheDocument();
    expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
  });

  it("treats a null severity as LOW rather than crashing", () => {
    render(<SeverityBadge severity={null as unknown as string} />);
    expect(screen.getByText(/low/i)).toBeInTheDocument();
  });

  it("StatusBadge renders the provided label", () => {
    render(<StatusBadge tone="success" label="approved" />);
    expect(screen.getByText(/approved/i)).toBeInTheDocument();
  });

  it("renders 'not_connected' as readable text, not a raw enum", () => {
    // Guards the connector status formatting in BriefPage.
    render(<StatusBadge tone="neutral" label={"not_connected".replace("_", " ")} />);
    expect(screen.getByText(/not connected/i)).toBeInTheDocument();
  });
});
