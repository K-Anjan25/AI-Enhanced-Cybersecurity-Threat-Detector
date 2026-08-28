import React from "react";
import { Network, ScanSearch, Bot } from "lucide-react";

/**
 * FeatureGrid — the Intelligence section (#intelligence), ported from
 * newfile.html: three green-top-border cards that lift on hover.
 */
const FEATURES = [
  {
    icon: Network,
    title: "Map what matters",
    body: "Continuously discover assets, relationships, and exposure paths across your digital estate.",
  },
  {
    icon: ScanSearch,
    title: "Prioritize with proof",
    body: "Correlate weak signals into evidence-backed risks your team can act on with confidence.",
  },
  {
    icon: Bot,
    title: "Respond at machine speed",
    body: "Let autonomous intelligence focus attention, shorten triage, and accelerate the next right move.",
  },
] as const;

const FeatureGrid: React.FC = () => (
  <section id="intelligence" className="scroll-mt-16 border-y border-white/10 bg-app-subtle/60">
    <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
      <div className="max-w-xl">
        <p className="tech-label text-accent-primary">Built for the moment before impact</p>
        <h2 className="mt-4 text-display-lg font-bold text-content-primary">
          A sharper security posture, without more noise.
        </h2>
      </div>

      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {FEATURES.map((f) => (
          <article
            key={f.title}
            className="rounded-sm border-t border-accent-primary/55 bg-app-surface/70 p-7 transition-transform duration-300 hover:-translate-y-1.5 hover:bg-app-surface-raised"
          >
            <f.icon className="h-6 w-6 text-accent-primary" aria-hidden="true" />
            <h3 className="mt-8 font-bold text-content-primary">{f.title}</h3>
            <p className="mt-3 leading-7 text-content-secondary">{f.body}</p>
          </article>
        ))}
      </div>
    </div>
  </section>
);

export default FeatureGrid;
