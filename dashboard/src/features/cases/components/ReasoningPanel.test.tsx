import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ReasoningPanel from "./ReasoningPanel";
import type { ReasoningResponse } from "../../../types/analyst";

const report = (over: Partial<ReasoningResponse> = {}): ReasoningResponse => ({
  base: 0.4,
  signals: [
    {
      signal: "threat_intel",
      label: "Threat intelligence",
      contribution: 0.2,
      detail: "Source address has a threat-intel risk score of 82/100.",
      evidence: { risk_score: 82 },
    },
    {
      signal: "correlation",
      label: "Related activity",
      contribution: 0.1,
      detail: "2 other alert(s) share the source 203.0.113.9.",
      evidence: { related_alerts: 2 },
    },
  ],
  unavailable: [
    {
      signal: "crown_jewel_reach",
      label: "Crown-jewel reachability",
      reason: "no assets are recorded, so no attack path can be computed",
    },
  ],
  confidence: 0.7,
  confidence_cap: 0.75,
  capped: false,
  coverage: "2 of 3 signals available",
  summary: "70% confidence, driven mainly by threat intelligence.",
  ...over,
});

describe("ReasoningPanel", () => {
  it("shows the arithmetic so an operator can check it by hand", () => {
    render(<ReasoningPanel reasoning={report()} />);

    expect(screen.getByText("40%")).toBeInTheDocument(); // baseline
    expect(screen.getByText(/\+20 pts/)).toBeInTheDocument();
    expect(screen.getByText(/\+10 pts/)).toBeInTheDocument();
    // 40 + 20 + 10 = 70
    expect(screen.getAllByText("70%").length).toBeGreaterThan(0);
  });

  it("names each contributing signal and its evidence", () => {
    render(<ReasoningPanel reasoning={report()} />);

    expect(screen.getByText("Threat intelligence")).toBeInTheDocument();
    expect(
      screen.getByText(/Source address has a threat-intel risk score of 82\/100/),
    ).toBeInTheDocument();
  });

  it("lists what could NOT be checked, with the reason", () => {
    render(<ReasoningPanel reasoning={report()} />);

    expect(screen.getByText(/Not checked \(1\)/)).toBeInTheDocument();
    expect(screen.getByText("Crown-jewel reachability")).toBeInTheDocument();
    expect(
      screen.getByText(/no assets are recorded, so no attack path can be computed/),
    ).toBeInTheDocument();
  });

  it("states that a blind spot is not evidence of safety", () => {
    render(<ReasoningPanel reasoning={report()} />);
    expect(
      screen.getByText(/Absence of a finding here is not evidence of safety/),
    ).toBeInTheDocument();
  });

  it("omits the blind-spot section when every signal was available", () => {
    render(<ReasoningPanel reasoning={report({ unavailable: [] })} />);
    expect(screen.queryByText(/Not checked/)).not.toBeInTheDocument();
  });

  it("explains when confidence was capped by thin coverage", () => {
    render(<ReasoningPanel reasoning={report({ capped: true, confidence: 0.75 })} />);
    expect(
      screen.getByText(/Capped at 75% — too few signals were available/),
    ).toBeInTheDocument();
  });

  it("renders a negative contribution as lowering confidence", () => {
    const r = report({
      signals: [
        {
          signal: "correlation",
          label: "Related activity",
          contribution: -0.05,
          detail: "No other alerts share this source; this looks isolated.",
          evidence: { related_alerts: 0 },
        },
      ],
    });
    render(<ReasoningPanel reasoning={r} />);
    expect(screen.getByText(/−5 pts/)).toBeInTheDocument();
  });

  it("surfaces a computation failure instead of showing an empty verdict", () => {
    render(
      <ReasoningPanel reasoning={null} error="backend unreachable" />,
    );
    expect(screen.getByText(/backend unreachable/)).toBeInTheDocument();
    expect(screen.getByText(/This is a\s+failure, not a clean result/)).toBeInTheDocument();
  });

  it("reports an error carried inside the payload", () => {
    render(<ReasoningPanel reasoning={report({ error: "db exploded", confidence: null })} />);
    expect(screen.getByText(/db exploded/)).toBeInTheDocument();
  });

  it("does not crash on a malformed payload mid-decision", () => {
    const broken = { summary: "partial" } as unknown as ReasoningResponse;
    render(<ReasoningPanel reasoning={broken} />);
    expect(screen.getByText("Why this verdict")).toBeInTheDocument();
  });

  it("shows a loading state rather than a premature zero", () => {
    render(<ReasoningPanel reasoning={null} loading />);
    expect(screen.getByText(/Working out the reasoning/)).toBeInTheDocument();
  });
});
