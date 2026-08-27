import React from "react";
import { useCountUp, useInView } from "../../hooks";

/**
 * TrustBar — the WooCommerce proof strip: real, verifiable numbers from this
 * repository (test suites, connectors, deployment modes) rendered with the
 * count-up hook. Nothing fabricated — this is the trust-signal pattern applied
 * to facts we can actually demonstrate.
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
    <div ref={ref} className="flex flex-col items-center text-center px-4 py-6">
      <p className="text-display-lg font-bold font-mono text-content-primary tabular-nums">
        {n}
        {suffix}
      </p>
      <p className="mt-1.5 text-xs text-content-secondary max-w-[14rem]">{label}</p>
    </div>
  );
};

const TrustBar: React.FC = () => (
  <section aria-label="Proof points" className="border-y border-line-subtle bg-app-surface">
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 grid grid-cols-2 lg:grid-cols-4 gap-y-6 divide-x divide-line-subtle">
      {STATS.map((s) => (
        <StatItem key={s.label} {...s} />
      ))}
    </div>
  </section>
);

export default TrustBar;
