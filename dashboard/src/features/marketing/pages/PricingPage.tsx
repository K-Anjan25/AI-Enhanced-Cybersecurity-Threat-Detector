import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, Minus } from 'lucide-react';
import { MarketingLayout } from '../MarketingLayout';
import { Accordion } from '../components/Accordion';
import { Reveal } from '../components/Reveal';
import { PageHero } from '../components/Shared';
import { COMPARISON, PRICING_FAQ, TIERS, type Tier } from '../content';

function PriceLine({ tier, annual }: { tier: Tier; annual: boolean }) {
  if (tier.monthly === null) return <p className="m-0 font-mono text-stat text-ink">Custom</p>;
  const amount = annual ? tier.annual : tier.monthly;
  return (
    <p className="m-0 font-mono text-stat text-ink tabular-nums">
      ${amount}
      <span className="font-sans text-body text-muted">
        {' '}
        / seat / month{annual && amount !== 0 ? ', billed yearly' : ''}
      </span>
    </p>
  );
}

/**
 * Pricing: a monthly/annual switch, three tier cards, a comparison table, and billing
 * questions. Prices are placeholders until sign-off.
 */
export function PricingPage() {
  const [annual, setAnnual] = useState(false);

  return (
    <MarketingLayout
      title="Pricing | AEGIS Threat Detection"
      description="Simple AEGIS plans: a free self-hosted Community tier, a Team plan for growing security teams, and Enterprise with SSO and response-time commitments."
    >
      <PageHero
        crumb="Pricing"
        title="Pricing that scales with your analysts, not your logs"
        lead="Pay for the people who use the console and for the support you need. Ingest volume is not billed separately."
      />

      <section
        aria-labelledby="plans-title"
        className="mx-auto w-full max-w-[1200px] px-6 pb-16 md:px-12 md:pb-[6rem]"
      >
        <h2 id="plans-title" className="sr-only">
          Plans
        </h2>
        <div
          role="group"
          aria-label="Billing period"
          className="mb-12 inline-flex items-center gap-1 rounded-pill border border-line bg-surface p-1"
        >
          <button
            type="button"
            aria-pressed={!annual}
            onClick={() => setAnnual(false)}
            className={`rounded-pill px-5 py-2 text-body font-semibold focus-visible:ring-2 ${!annual ? 'bg-accent text-onAccent' : 'text-muted'}`}
          >
            Monthly
          </button>
          <button
            type="button"
            aria-pressed={annual}
            onClick={() => setAnnual(true)}
            className={`inline-flex items-center gap-2 rounded-pill px-5 py-2 text-body font-semibold focus-visible:ring-2 ${annual ? 'bg-accent text-onAccent' : 'text-muted'}`}
          >
            Annual
            <span className={`font-mono text-caption ${annual ? 'text-onAccent' : 'text-accent'}`}>
              save 13%
            </span>
          </button>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {TIERS.map((tier, index) => (
            <Reveal key={tier.name} delayMs={index * 90} className="h-full">
              <article
                aria-labelledby={`tier-${tier.name}`}
                className={`relative flex h-full flex-col rounded-card border bg-surface p-6 ${tier.featured ? 'border-accent md:-mt-4' : 'border-line'}`}
              >
                {tier.featured && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-pill bg-accent px-3 py-1 font-mono text-caption font-semibold text-onAccent">
                    Most popular
                  </span>
                )}
                <h3 id={`tier-${tier.name}`} className="m-0 text-display text-ink">
                  {tier.name}
                </h3>
                <p className="mb-0 mt-2 min-h-[3.25rem] text-body-sm text-muted">
                  {tier.description}
                </p>
                <div className="mt-4">
                  <PriceLine tier={tier} annual={annual} />
                </div>
                <ul className="mb-8 mt-6 grid flex-1 list-none gap-3 p-0">
                  {tier.included.map((feature) => (
                    <li
                      key={feature}
                      className="grid grid-cols-[20px_1fr] gap-3 text-body text-muted"
                    >
                      <Check aria-hidden="true" className="mt-1 size-icon-sm text-accent" />
                      <span>{feature}</span>
                    </li>
                  ))}
                  {tier.excluded.map((feature) => (
                    <li
                      key={feature}
                      className="grid grid-cols-[20px_1fr] gap-3 text-body text-muted"
                    >
                      <Minus aria-hidden="true" className="mt-1 size-icon-sm" />
                      <span>
                        {feature} <span className="sr-only">(not included)</span>
                      </span>
                    </li>
                  ))}
                </ul>
                <Link
                  to="/contact"
                  className={`inline-flex items-center justify-center rounded-pill px-6 py-3 text-caption font-semibold uppercase tracking-widest no-underline focus-visible:ring-2 ${tier.featured ? 'bg-accent text-onAccent' : 'border border-accent text-accent hover:bg-base'}`}
                >
                  {tier.cta}
                </Link>
              </article>
            </Reveal>
          ))}
        </div>

        {/* A real table, so screen-reader users can move by row and column. */}
        <Reveal className="mt-16 min-w-0">
          <div className="marketing-scroll rounded-card border border-line">
            <table className="w-full min-w-[560px] border-collapse bg-surface text-left">
              <caption className="px-6 py-4 text-left text-h2 font-semibold text-ink">
                Compare plans
              </caption>
              <thead>
                <tr className="bg-base">
                  <th scope="col" className="px-6 py-4 text-body font-semibold text-ink">
                    Capability
                  </th>
                  {TIERS.map((tier) => (
                    <th
                      key={tier.name}
                      scope="col"
                      className="px-6 py-4 text-center text-body font-semibold text-ink"
                    >
                      {tier.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARISON.map(([label, ...values]) => (
                  <tr key={label} className="border-t border-line">
                    <th
                      scope="row"
                      className="px-6 py-4 text-left text-body font-semibold text-ink"
                    >
                      {label}
                    </th>
                    {values.map((value, column) => (
                      <td key={`${label}-${column}`} className="px-6 py-4 text-center text-muted">
                        {value ? (
                          <>
                            <Check
                              aria-hidden="true"
                              className="mx-auto size-icon-sm text-accent"
                            />
                            <span className="sr-only">Included</span>
                          </>
                        ) : (
                          <>
                            <Minus aria-hidden="true" className="mx-auto size-icon-sm" />
                            <span className="sr-only">Not included</span>
                          </>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>
      </section>

      <section
        aria-labelledby="pricing-faq-title"
        className="mx-auto w-full max-w-[860px] px-6 pb-16 md:px-12 md:pb-[6rem]"
      >
        <Reveal>
          <div className="mb-12 text-center">
            <p className="m-0 font-mono text-caption uppercase tracking-widest text-accent">
              Billing FAQ
            </p>
            <h2 id="pricing-faq-title" className="mt-3 text-display">
              Plans, seats and billing
            </h2>
          </div>
        </Reveal>
        <Accordion items={PRICING_FAQ} />
      </section>
    </MarketingLayout>
  );
}
