import React from "react";
import { Network, ShieldAlert, KeyRound, Server } from "lucide-react";
import type { CaseContext } from "../types/analyst";

/**
 * What a case means for *this* organisation.
 *
 * Renders only findings the backend actually derived — an absent key means the
 * module had no data, and we show nothing rather than a reassuring placeholder.
 * If nothing is present the component renders null, so callers can drop it in
 * unconditionally.
 */
export interface CaseImpactProps {
  context?: CaseContext | null;
  /** `compact` suits list rows; `full` suits the case and brief detail views. */
  variant?: "compact" | "full";
  className?: string;
}

const Line: React.FC<{ icon: React.ReactNode; tone?: "critical" | "warning" | "default"; children: React.ReactNode }> = ({
  icon,
  tone = "default",
  children,
}) => {
  const toneClass =
    tone === "critical"
      ? "text-status-critical"
      : tone === "warning"
        ? "text-status-warning"
        : "text-content-secondary";
  return (
    <li className="flex items-start gap-2 text-xs leading-relaxed">
      <span className={`shrink-0 mt-0.5 ${toneClass}`} aria-hidden>
        {icon}
      </span>
      <span className="text-content-secondary">{children}</span>
    </li>
  );
};

export const CaseImpact: React.FC<CaseImpactProps> = ({ context, variant = "full", className }) => {
  if (!context) return null;

  const { crown_jewel_reach: reach, posture, leaked_credentials: leaked, affected_assets: assets } = context;
  if (!reach && !posture && !leaked?.length && !assets?.length) return null;

  const compact = variant === "compact";

  return (
    <div className={className}>
      {!compact && (
        <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary mb-1.5">
          What this means for you
        </p>
      )}
      <ul className="space-y-1.5">
        {reach && (
          <Line icon={<Network size={13} />} tone={reach.hops <= 2 ? "critical" : "warning"}>
            <strong className="text-content-primary">
              {reach.hops} {reach.hops === 1 ? "hop" : "hops"} from {reach.crown_jewel}
            </strong>
            {reach.techniques && reach.techniques.length > 0 && (
              <span className="font-mono text-[11px] text-content-tertiary"> · {reach.techniques.join(" → ")}</span>
            )}
          </Line>
        )}

        {posture && (
          <Line icon={<ShieldAlert size={13} />} tone="warning">
            Posture <strong className="text-content-primary font-mono">{posture.current_score}</strong> → drops to{" "}
            <strong className="text-content-primary font-mono">{posture.projected_score}</strong> while unresolved
            <span className="text-content-tertiary"> ({posture.points_at_risk} pts at risk)</span>
          </Line>
        )}

        {leaked && leaked.length > 0 && (
          <Line icon={<KeyRound size={13} />} tone="critical">
            <strong className="text-content-primary font-mono">{leaked[0].identity}</strong> is already exposed —{" "}
            {leaked[0].finding_type.replace(/_/g, " ")} on {leaked[0].source}
            {leaked.length > 1 && <span className="text-content-tertiary"> (+{leaked.length - 1} more)</span>}
          </Line>
        )}

        {!compact && assets && assets.length > 0 && (
          <Line icon={<Server size={13} />}>
            Highest-value asset: <strong className="text-content-primary">{assets[0].name}</strong>
            <span className="text-content-tertiary"> (criticality {assets[0].criticality}/5</span>
            {assets[0].owner && <span className="text-content-tertiary">, {assets[0].owner}</span>}
            <span className="text-content-tertiary">)</span>
          </Line>
        )}
      </ul>
    </div>
  );
};

export default CaseImpact;
