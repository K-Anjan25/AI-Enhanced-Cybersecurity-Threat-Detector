import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import CaseImpact from "./CaseImpact";
import type { CaseContext } from "../types/analyst";

describe("CaseImpact", () => {
  it("renders nothing when the backend supplied no context", () => {
    const { container } = render(<CaseImpact context={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when every module came back empty", () => {
    const { container } = render(<CaseImpact context={{}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("states the distance to the crown jewel", () => {
    const context: CaseContext = {
      crown_jewel_reach: { path_id: 1, hops: 2, crown_jewel: "dc01", techniques: ["T1190", "T1021"] },
    };
    render(<CaseImpact context={context} />);
    expect(screen.getByText("2 hops from dc01")).toBeInTheDocument();
    expect(screen.getByText(/T1190 → T1021/)).toBeInTheDocument();
  });

  it("uses the singular for a single hop", () => {
    render(<CaseImpact context={{ crown_jewel_reach: { path_id: 1, hops: 1, crown_jewel: "dc01" } }} />);
    expect(screen.getByText("1 hop from dc01")).toBeInTheDocument();
  });

  it("shows the posture points at risk", () => {
    const context: CaseContext = {
      posture: { current_score: 72, points_at_risk: 8, projected_score: 64, trend: "stable" },
    };
    render(<CaseImpact context={context} />);
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByText("64")).toBeInTheDocument();
    expect(screen.getByText(/8 pts at risk/)).toBeInTheDocument();
  });

  it("surfaces a leaked identity and counts the rest", () => {
    const context: CaseContext = {
      leaked_credentials: [
        {
          finding_id: 1,
          identity: "victim@acme.com",
          finding_type: "leaked_credential",
          severity: "CRITICAL",
          title: "t",
          source: "paste_site",
        },
        {
          finding_id: 2,
          identity: "other@acme.com",
          finding_type: "leaked_credential",
          severity: "HIGH",
          title: "t",
          source: "paste_site",
        },
      ],
    };
    render(<CaseImpact context={context} />);
    expect(screen.getByText("victim@acme.com")).toBeInTheDocument();
    expect(screen.getByText(/leaked credential on paste_site/)).toBeInTheDocument();
    expect(screen.getByText("(+1 more)")).toBeInTheDocument();
  });

  it("omits the asset line in the compact variant used by list rows", () => {
    const context: CaseContext = {
      crown_jewel_reach: { path_id: 1, hops: 2, crown_jewel: "dc01" },
      affected_assets: [{ id: 1, name: "fileserver01", criticality: 4 }],
    };
    render(<CaseImpact context={context} variant="compact" />);
    expect(screen.getByText("2 hops from dc01")).toBeInTheDocument();
    expect(screen.queryByText(/fileserver01/)).not.toBeInTheDocument();
  });
});
