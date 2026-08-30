import React from "react";
import { Check, Minus, TriangleAlert, EyeOff } from "lucide-react";
import { Card, Term, cn } from "../../../components/ui";
import type { ReasoningResponse } from "../../../types/analyst";

/**
 * The audit trail behind a case's confidence.
 *
 * A verdict of "87%, isolate the host" with nothing behind it asks to be
 * trusted on faith. This panel shows the arithmetic: the baseline, every
 * signal that moved it and by how much, and — the part that matters most —
 * every signal that could NOT be consulted, with the reason.
 *
 * A 70% built from two signals with four blind spots is a different claim
 * from a 70% built from six. Both used to render as "70%".
 */

const pct = (v: number): string => `${v >= 0 ? "+" : "\u2212"}${Math.abs(Math.round(v * 100))}`;

const Contribution: React.FC<{ value: number }> = ({ value }) => {
  const raises = value > 0;
  const neutral = Math.abs(value) < 0.005;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 tabular-nums font-medium shrink-0",
        neutral
          ? "text-content-tertiary"
          : raises
            ? "text-status-critical"
            : "text-status-success",
      )}
      title={raises ? "Raises confidence this is a real incident" : "Lowers confidence"}
    >
      {neutral ? <Minus size={12} aria-hidden /> : <Check size={12} aria-hidden />}
      {pct(value)} pts
    </span>
  );
};

interface Props {
  reasoning: ReasoningResponse | null;
  loading?: boolean;
  error?: string | null;
}

export const ReasoningPanel: React.FC<Props> = ({ reasoning, loading, error }) => {
  if (loading) {
    return (
      <Card className="p-5">
        <h2 className="text-sm font-bold font-display text-content-primary mb-2">
          Why this verdict
        </h2>
        <p className="text-xs text-content-tertiary">Working out the reasoning…</p>
      </Card>
    );
  }

  if (error || reasoning?.error) {
    return (
      <Card className="p-5">
        <h2 className="text-sm font-bold font-display text-content-primary mb-2">
          Why this verdict
        </h2>
        <div className="flex items-start gap-2 text-xs text-status-critical">
          <TriangleAlert size={14} className="shrink-0 mt-px" aria-hidden />
          <span>
            The reasoning could not be computed — {error || reasoning?.error}. This is a
            failure, not a clean result.
          </span>
        </div>
      </Card>
    );
  }

  if (!reasoning) return null;

  // Tolerate a malformed payload: a missing array must render as "nothing to
  // show", never crash the case page an operator is mid-decision on.
  const base = typeof reasoning.base === "number" ? reasoning.base : 0;
  const signals = Array.isArray(reasoning.signals) ? reasoning.signals : [];
  const unavailable = Array.isArray(reasoning.unavailable) ? reasoning.unavailable : [];
  const { confidence, capped, confidence_cap, coverage } = reasoning;

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-sm font-bold font-display text-content-primary">
            Why this verdict
          </h2>
          <p className="text-xs text-content-secondary mt-1 max-w-xl">{reasoning.summary}</p>
        </div>
        {confidence !== null && (
          <div className="text-right shrink-0">
            <p className="text-3xl font-bold tabular-nums leading-none text-content-primary">
              {Math.round(confidence * 100)}%
            </p>
            <p className="tech-label text-content-tertiary mt-1">
              <Term>confidence</Term>
            </p>
          </div>
        )}
      </div>

      {/* The arithmetic, so an operator can check it by hand. */}
      <div className="space-y-1.5 text-xs">
        <div className="flex items-center justify-between gap-3 text-content-tertiary">
          <span>Starting point (no evidence)</span>
          <span className="tabular-nums">{Math.round(base * 100)}%</span>
        </div>

        {signals.map((s) => (
          <div
            key={s.signal}
            className="flex items-start justify-between gap-3 border-t border-line-subtle pt-1.5"
          >
            <div className="min-w-0">
              <p className="font-medium text-content-primary">{s.label}</p>
              <p className="text-content-secondary mt-0.5">{s.detail}</p>
            </div>
            <Contribution value={s.contribution} />
          </div>
        ))}

        {confidence !== null && (
          <div className="flex items-center justify-between gap-3 border-t border-line-strong pt-1.5 font-medium text-content-primary">
            <span>Confidence</span>
            <span className="tabular-nums">{Math.round(confidence * 100)}%</span>
          </div>
        )}
      </div>

      {capped && confidence_cap != null && (
        <p className="text-xs text-content-tertiary">
          Capped at {Math.round(confidence_cap * 100)}% — too few signals were available to
          justify more certainty.
        </p>
      )}

      {/* The honest half: what we could not see. */}
      {unavailable.length > 0 && (
        <div className="border-t border-line-subtle pt-3">
          <div className="flex items-center gap-1.5 mb-2">
            <EyeOff size={13} className="text-content-tertiary" aria-hidden />
            <h3 className="tech-label text-content-tertiary">
              Not checked ({unavailable.length})
            </h3>
          </div>
          <ul className="space-y-1 text-xs">
            {unavailable.map((u) => (
              <li key={u.signal} className="flex gap-2">
                <span className="text-content-tertiary shrink-0">·</span>
                <span className="text-content-secondary">
                  <span className="font-medium text-content-primary">{u.label}</span> — {u.reason}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-content-tertiary mt-2">
            These were not consulted. Absence of a finding here is not evidence of safety.
          </p>
        </div>
      )}

      {coverage && <p className="text-[11px] text-content-tertiary">{coverage}.</p>}
    </Card>
  );
};

export default ReasoningPanel;
