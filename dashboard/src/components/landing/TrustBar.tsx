import React from "react";
import { useCountUp, useInView } from "../../hooks";

/**
 * TrustBar — proof strip of real, verifiable numbers (test suites, connectors,
 * run modes) in Apple style: quiet dividers, tabular mono numerals.
 */
const STATS = [
  { value: 114, suffix: "", label: "Backend tests passing" },
  { value: 13, suffix: "", label: "ML service tests passing" },
  { value: 4, suffix: "", label: "Connectors (Okta, EDR, GuardDuty, WAF)" },
  { value: 2, suffix: "", label: "Run modes — REST or Kafka streaming" },
] as const;

const StatItem: React.FC<{ value: number; suffix: string; label: string }> = ({ value, suffix, label }) => {
  const [ref, inView] = useInView<HTMLDivElement>();
  const n = useCountUp(value, inView);
  return (
    <div ref={ref} className="flex flex-col items-center text-center px-4 py-8">
      <p className="text-4xl font-semibold font-mono text-content-primary tabular-nums tracking-tight">
        {n}
        {suffix}
      </p>
      <p className="mt-2 text-xs text-content-secondary max-w-[13rem]">{label}</p>
    </div>
  );
};

const TrustBar: React.FC = () => (
  <section aria-label="Proof points" className="bg-app-surface border-y border-line-subtle">
    <div className="max-w-5xl mx-auto px-4 sm:px-6 grid grid-cols-2 lg:grid-cols-4 divide-y lg:divide-y-0 lg:divide-x divide-line-subtle">
      {STATS.map((s) => (
        <StatItem key={s.label} {...s} />
      ))}
    </div>
  </section>
);

export default TrustBar;
