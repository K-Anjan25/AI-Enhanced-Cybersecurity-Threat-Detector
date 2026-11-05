import { Link } from 'react-router-dom';
import { CircleCheck } from 'lucide-react';
import type { SplitSection } from '../content';
import { Reveal } from './Reveal';

/** Inner-page heading block with a breadcrumb. */
export function PageHero({ crumb, title, lead }: { crumb: string; title: string; lead: string }) {
  return (
    <section className="relative isolate overflow-hidden pb-16 pt-[7.5rem]">
      <div className="mx-auto w-full max-w-[1200px] px-6 md:px-12">
        <p className="mb-4 font-mono text-body-sm font-semibold text-muted">
          <Link to="/" className="text-muted hover:text-accent">
            Home
          </Link>{' '}
          / {crumb}
        </p>
        <Reveal>
          <h1 className="max-w-[22ch] text-display md:text-hero">{title}</h1>
        </Reveal>
        <Reveal delayMs={80}>
          <p className="mt-4 max-w-[60ch] text-body-sm text-muted md:text-body">{lead}</p>
        </Reveal>
      </div>
    </section>
  );
}

/** Two-column row with copy on one side and an image on the other. One column on narrow screens. */
export function SplitFeature({
  section,
  reverse = false,
}: {
  section: SplitSection;
  reverse?: boolean;
}) {
  return (
    <div id={section.id} className="grid items-center gap-12 md:grid-cols-2 md:gap-16">
      <Reveal className={reverse ? 'md:order-2' : ''}>
        <span className="mb-3 inline-block font-mono text-caption uppercase tracking-widest text-accent">
          {section.eyebrow}
        </span>
        <h2 className="text-display">{section.title}</h2>
        <p className="mt-3 text-body text-muted">{section.body}</p>
        <ul className="mt-6 grid list-none gap-3 p-0">
          {section.points.map(([strong, rest]) => (
            <li key={strong} className="grid grid-cols-[20px_1fr] gap-3 text-muted">
              <CircleCheck aria-hidden="true" className="mt-1 size-icon-sm text-accent" />
              <span>
                <strong className="text-ink">{strong}</strong> {rest}
              </span>
            </li>
          ))}
        </ul>
      </Reveal>
      <Reveal delayMs={120} className={reverse ? 'md:order-1' : ''}>
        {/* Placeholder imagery. Replace with product screenshots before launch. */}
        <img
          src={section.image}
          alt={section.alt}
          width={960}
          height={600}
          loading="lazy"
          decoding="async"
          className="aspect-[16/10] w-full rounded-card border border-line object-cover"
        />
      </Reveal>
    </div>
  );
}
