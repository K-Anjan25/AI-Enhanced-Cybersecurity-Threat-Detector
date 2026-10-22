import { Link } from 'react-router-dom';
import { BrainCircuit, GitBranch, Layers, Plug, Search, UserLock } from 'lucide-react';
import { MarketingLayout } from '../MarketingLayout';
import { Reveal } from '../components/Reveal';
import { SplitFeature, PageHero } from '../components/Shared';
import { ARCHITECTURE_STEPS, FEATURE_CARDS, FEATURE_SECTIONS } from '../content';

const ICONS = [BrainCircuit, Layers, Search, GitBranch, Plug, UserLock] as const;

/** Product features: an overview grid, the three detail rows, the capture-to-case flow, and a call to action. */
export function FeaturesPage() {
  return (
    <MarketingLayout
      title="Features | AEGIS Threat Detection"
      description="Explore AEGIS features: model-based anomaly detection, grouped alert triage, threat hunting, audited exports, model rollback and role-based governance."
    >
      <PageHero
        crumb="Features"
        title="Everything between the first packet and the final verdict"
        lead="AEGIS covers detection, triage, investigation and governance in one console, and keeps the evidence for every decision."
      />

      <section
        aria-labelledby="feature-grid-title"
        className="mx-auto w-full max-w-[1200px] px-6 pb-16 md:px-12 md:pb-[6rem]"
      >
        <h2 id="feature-grid-title" className="sr-only">
          Feature overview
        </h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {FEATURE_CARDS.map((feature, index) => {
            const Icon = ICONS[index] ?? BrainCircuit;
            return (
              <Reveal key={feature.title} delayMs={(index % 3) * 80} className="h-full">
                <article className="h-full rounded-card border border-line bg-surface p-6">
                  <span
                    className="mb-4 grid size-12 place-items-center rounded-card border border-accent text-accent"
                    aria-hidden="true"
                  >
                    <Icon className="size-icon-md" />
                  </span>
                  <h3 className="m-0 text-h2 font-semibold text-ink">{feature.title}</h3>
                  <p className="mb-0 mt-2 text-body text-muted">{feature.body}</p>
                </article>
              </Reveal>
            );
          })}
        </div>
      </section>

      <section aria-labelledby="feature-details-title" className="border-y border-line bg-surface">
        <div className="mx-auto grid w-full max-w-[1200px] gap-16 px-6 py-16 md:px-12 md:py-[6rem]">
          <h2 id="feature-details-title" className="sr-only">
            Feature details
          </h2>
          {FEATURE_SECTIONS.map((section, index) => (
            <SplitFeature key={section.eyebrow} section={section} reverse={index % 2 === 1} />
          ))}
        </div>
      </section>

      <section
        aria-labelledby="flow-title"
        className="mx-auto w-full max-w-[1200px] px-6 py-16 md:px-12 md:py-[6rem]"
      >
        <Reveal>
          <p className="m-0 font-mono text-caption uppercase tracking-widest text-accent">
            Architecture at a glance
          </p>
          <h2 id="flow-title" className="mt-3 text-display">
            From capture to case, in four stages
          </h2>
        </Reveal>
        <ol className="mt-12 grid list-none gap-4 p-0 md:grid-cols-2 lg:grid-cols-4">
          {ARCHITECTURE_STEPS.map(([title, body], index) => (
            <Reveal key={title} delayMs={index * 80} className="h-full">
              <li className="h-full rounded-card border-t-2 border-accent bg-surface p-6">
                <h3 className="mt-2 text-h2 font-semibold text-ink">{title}</h3>
                <p className="mb-0 mt-2 text-body-sm text-muted">{body}</p>
              </li>
            </Reveal>
          ))}
        </ol>
      </section>

      <section
        aria-labelledby="features-cta-title"
        className="mx-auto w-full max-w-[1200px] px-6 pb-16 md:px-12 md:pb-[6rem]"
      >
        <Reveal>
          <div className="rounded-card border border-accent bg-surface p-8 text-center md:p-12">
            <h2 id="features-cta-title" className="text-display">
              Ready to see your own traffic scored?
            </h2>
            <p className="mx-auto mb-0 mt-3 max-w-[60ch] text-body text-muted">
              Start with the free tier, or book a walkthrough with an engineer.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link
                to="/pricing"
                className="inline-flex items-center rounded-pill bg-accent px-6 py-3 text-caption font-semibold uppercase tracking-widest text-onAccent no-underline focus-visible:ring-2"
              >
                View pricing
              </Link>
              <Link
                to="/contact"
                className="inline-flex items-center rounded-pill border border-accent px-6 py-3 text-caption font-semibold uppercase tracking-widest text-accent no-underline hover:bg-base focus-visible:ring-2"
              >
                Book a demo
              </Link>
            </div>
          </div>
        </Reveal>
      </section>
    </MarketingLayout>
  );
}
