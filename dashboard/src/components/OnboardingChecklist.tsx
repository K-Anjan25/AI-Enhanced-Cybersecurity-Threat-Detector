import React from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, ArrowRight, X } from "lucide-react";

export interface OnboardingStep {
  id: string;
  label: string;
  hint?: string;
  to?: string;
  done: boolean;
}

interface Props {
  steps: OnboardingStep[];
  onDismiss: () => void;
}

/**
 * First-run checklist — walks the analyst loop end-to-end:
 * sense → case → decision → record → report. Every step's completion is
 * derived from real data or real navigation, never simulated. Dismissable;
 * hides itself once everything is done.
 */
const OnboardingChecklist: React.FC<Props> = ({ steps, onDismiss }) => {
  const doneCount = steps.filter((s) => s.done).length;
  if (doneCount === steps.length) return null;

  return (
    <section
      aria-label="Getting started with NOCTRA"
      className="bg-app-surface rounded-2xl border border-line-subtle shadow-card p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold font-display text-content-primary">
            See the loop end-to-end
          </h2>
          <p className="text-xs text-content-tertiary mt-0.5">
            {doneCount} of {steps.length} done — each step checks real data, nothing is simulated.
          </p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss getting-started checklist"
          title="Dismiss"
          className="text-content-tertiary hover:text-content-primary transition cursor-pointer p-1"
        >
          <X size={14} aria-hidden />
        </button>
      </div>

      <ol className="mt-3 divide-y divide-line-subtle">
        {steps.map((step) => (
          <li key={step.id} className="flex items-center gap-3 py-2.5">
            {step.done ? (
              <CheckCircle2 size={15} className="text-status-success shrink-0" aria-hidden />
            ) : (
              <Circle size={15} className="text-content-tertiary shrink-0" aria-hidden />
            )}
            <div className="min-w-0 flex-1">
              <p
                className={`text-xs font-medium truncate ${
                  step.done ? "text-content-tertiary line-through" : "text-content-primary"
                }`}
              >
                {step.label}
              </p>
              {step.hint && !step.done && (
                <p className="text-[11px] text-content-tertiary truncate">{step.hint}</p>
              )}
            </div>
            {!step.done && step.to && (
              <Link
                to={step.to}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent-secondary hover:underline shrink-0"
              >
                Go <ArrowRight size={11} aria-hidden />
              </Link>
            )}
            {step.done && (
              <span className="text-[10px] font-mono uppercase tracking-wider text-status-success shrink-0">
                done
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
};

export default OnboardingChecklist;
