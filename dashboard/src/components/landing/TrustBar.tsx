import React from "react";

/**
 * TrustBar — the stats band (#platform), ported from newfile.html.
 * Capability claims only (24/7, <5 min, 360°, 1 view) — no fabricated metrics.
 */
const STATS = [
  { value: "24/7", label: "Continuous monitoring" },
  { value: "< 5 min", label: "Signal-to-insight" },
  { value: "360°", label: "Attack-surface context" },
  { value: "1 view", label: "For your security posture" },
] as const;

const TrustBar: React.FC = () => (
  <section
    id="platform"
    aria-label="Coverage at a glance"
    className="scroll-mt-16 border-y border-white/10 bg-app-subtle/70"
  >
    <div className="mx-auto grid max-w-7xl grid-cols-2 divide-x divide-y divide-white/10 px-5 md:grid-cols-4 md:divide-y-0 lg:px-8">
      {STATS.map((s) => (
        <div key={s.label} className="py-7 text-center">
          <p className="text-2xl font-bold tabular-nums tracking-tight text-accent-primary">
            {s.value}
          </p>
          <p className="tech-label mt-2 text-content-tertiary">{s.label}</p>
        </div>
      ))}
    </div>
  </section>
);

export default TrustBar;
