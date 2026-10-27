import { Link } from 'react-router-dom';
import { ArrowUp, Mail, MapPin } from 'lucide-react';
import { FOOTER_COLUMNS, OFFICES, SALES_EMAIL, SOCIAL_LINKS, type Office } from '../content';
import { prefersReducedMotion } from '../hooks';
import { NewsletterForm } from './NewsletterForm';
import { SocialIcon } from './SocialIcon';

/** Projects longitude and latitude onto the dot map as percentages (equirectangular). */
export function project(lat: number, lon: number): { x: number; y: number } {
  return { x: ((lon + 180) / 360) * 100, y: ((90 - lat) / 180) * 100 };
}

const COLS = 60;
const ROWS = 26;

/**
 * Decorative dot-matrix map with the offices pinned on it. It is hidden from assistive
 * technology, and the same offices are listed in text beside it.
 */
export function DotMap() {
  const dots: Array<{ x: number; y: number }> = [];
  for (let row = 4; row < 22; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      // A fixed pattern, so the map looks the same on every render.
      if ((col * 7 + row * 13) % 5 !== 0) dots.push({ x: col * 1.6 + 0.8, y: row * 1.6 + 0.8 });
    }
  }
  return (
    <div
      className="relative aspect-[2/1] w-full overflow-hidden rounded-card border border-line bg-base"
      aria-hidden="true"
    >
      <svg
        viewBox={`0 0 ${COLS * 1.6} ${ROWS * 1.6}`}
        preserveAspectRatio="none"
        className="absolute inset-0 size-full"
      >
        {dots.map((dot) => (
          <circle
            key={`${dot.x}-${dot.y}`}
            cx={dot.x}
            cy={dot.y}
            r={0.42}
            className="fill-accent opacity-40"
          />
        ))}
      </svg>
      {OFFICES.map((office: Office) => {
        const point = project(office.lat, office.lon);
        return (
          <div
            key={office.city}
            className="absolute flex -translate-x-1/2 -translate-y-full flex-col items-center gap-1"
            style={{ left: `${point.x}%`, top: `${point.y}%` }}
          >
            <MapPin className="size-icon-md text-accent" />
            <span className="whitespace-nowrap rounded-input border border-line bg-base px-2 py-[2px] font-mono text-caption text-ink">
              {office.city}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Fat footer: brand and newsletter, four link columns, the office map, social links, legal. */
export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="mt-auto border-t border-line bg-base" aria-labelledby="footer-heading">
      <h2 id="footer-heading" className="sr-only">
        Site footer
      </h2>
      <div className="mx-auto w-full max-w-[1200px] px-6 pb-6 pt-16 md:px-12">
        <div className="grid gap-12 lg:grid-cols-[1.4fr_repeat(4,1fr)]">
          <div className="flex flex-col gap-4">
            <p className="m-0 flex items-center gap-2 text-h2 font-semibold tracking-widest text-ink">
              <img
                src="/aegis-logo.png"
                alt=""
                width="32"
                height="32"
                className="size-8 rounded-input"
              />
              AEGIS
            </p>
            <p className="m-0 max-w-[36ch] text-body text-muted">
              AI-enhanced threat detection for security teams. Score traffic and logs in-house, and
              keep every verdict on record.
            </p>
            <div className="mt-2 flex flex-col gap-3">
              <h3 className="m-0 text-caption font-semibold uppercase tracking-widest text-ink">
                Security briefing
              </h3>
              <p className="m-0 text-body-sm text-muted">
                One email a month on detection research and product changes. Unsubscribe at any
                time.
              </p>
              <NewsletterForm variant="footer" />
            </div>
          </div>

          {FOOTER_COLUMNS.map((column) => (
            <nav
              key={column.title}
              aria-label={`${column.title} links`}
              className="flex flex-col gap-3"
            >
              <h3 className="m-0 text-caption font-semibold uppercase tracking-widest text-ink">
                {column.title}
              </h3>
              <ul className="m-0 grid list-none gap-2 p-0">
                {column.links.map(([label, target]) => (
                  <li key={label}>
                    <Link
                      to={target}
                      className="text-body text-muted no-underline hover:text-accent hover:underline"
                    >
                      {label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-12 grid gap-12 md:grid-cols-[1.6fr_1fr]">
          <section aria-labelledby="footer-map-heading" className="flex flex-col gap-3">
            <h3
              id="footer-map-heading"
              className="m-0 text-caption font-semibold uppercase tracking-widest text-ink"
            >
              Where we work
            </h3>
            <DotMap />
          </section>
          <section aria-labelledby="footer-offices-heading" className="flex flex-col gap-4">
            <h3
              id="footer-offices-heading"
              className="m-0 text-caption font-semibold uppercase tracking-widest text-ink"
            >
              Offices
            </h3>
            <ul className="m-0 grid list-none gap-3 p-0">
              {OFFICES.map((office) => (
                <li key={office.city} className="flex gap-3">
                  <MapPin aria-hidden="true" className="mt-1 size-icon-sm shrink-0 text-accent" />
                  <div>
                    <p className="m-0 font-semibold text-ink">
                      {office.city}, {office.country}
                    </p>
                    <p className="m-0 text-body-sm text-muted">{office.note}</p>
                  </div>
                </li>
              ))}
            </ul>
            <ul className="m-0 flex list-none flex-wrap gap-3 p-0" aria-label="Social media">
              {SOCIAL_LINKS.map((link) => (
                <li key={link.label}>
                  <a
                    href={link.href}
                    aria-label={link.label}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="grid size-12 place-items-center rounded-pill border border-line text-ink hover:border-accent hover:text-accent focus-visible:ring-2"
                  >
                    <SocialIcon name={link.icon} />
                  </a>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div className="mt-12 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6 text-body-sm text-muted">
          <p className="m-0">
            © {year} AEGIS. All rights reserved.{' '}
            <a
              href={`mailto:${SALES_EMAIL}`}
              className="inline-flex items-center gap-1 text-accent"
            >
              <Mail aria-hidden="true" className="size-icon-sm" />
              {SALES_EMAIL}
            </a>
          </p>
          <nav aria-label="Legal" className="flex flex-wrap gap-4">
            <Link to="/contact" className="text-muted no-underline hover:text-accent">
              Privacy
            </Link>
            <Link to="/contact" className="text-muted no-underline hover:text-accent">
              Terms
            </Link>
            <Link to="/contact" className="text-muted no-underline hover:text-accent">
              Security
            </Link>
          </nav>
          <button
            type="button"
            onClick={() =>
              window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
            }
            className="inline-flex items-center gap-2 rounded-pill border border-line px-4 py-2 text-body-sm font-semibold text-accent hover:border-accent focus-visible:ring-2"
          >
            <ArrowUp aria-hidden="true" className="size-icon-sm" />
            Back to top
          </button>
        </div>
      </div>
    </footer>
  );
}
