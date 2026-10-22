import { useId, useState, type FormEvent } from 'react';
import { MapPin, Send } from 'lucide-react';
import { MarketingLayout } from '../MarketingLayout';
import { DotMap } from '../components/SiteFooter';
import { Reveal } from '../components/Reveal';
import { PageHero } from '../components/Shared';
import { CONTACT_PATH, IDLE, isEmail, submitForm, type FormStatus } from '../components/forms';
import { OFFICES, SALES_EMAIL, SECURITY_EMAIL } from '../content';

interface ContactValues {
  name: string;
  email: string;
  company: string;
  topic: 'demo' | 'deploy' | 'support' | 'security';
  message: string;
  consent: boolean;
}

const EMPTY: ContactValues = {
  name: '',
  email: '',
  company: '',
  topic: 'demo',
  message: '',
  consent: false,
};
type FieldKey = 'name' | 'email' | 'message' | 'consent';

/** Checks every field and returns the messages keyed by field. */
function validate(values: ContactValues): Partial<Record<FieldKey, string>> {
  const errors: Partial<Record<FieldKey, string>> = {};
  if (values.name.trim().length < 2) errors.name = 'Enter your name.';
  if (!isEmail(values.email)) errors.email = 'Enter a valid work email address.';
  if (values.message.trim().length < 10)
    errors.message = 'Tell us a little more, at least 10 characters.';
  if (!values.consent) errors.consent = 'Please confirm you agree to be contacted.';
  return errors;
}

const FIELD_INPUT =
  'w-full rounded-input border border-line bg-base px-4 py-3 text-body text-ink placeholder:text-muted focus-visible:ring-2';
const FIELD_ERROR = 'm-0 text-body-sm text-severityText-critical';

/**
 * Contact form with per-field validation, focus moved to the first invalid field,
 * a honeypot, and a live status region. Nothing is reported as sent unless the server
 * accepts it.
 */
export function ContactPage() {
  const uid = useId();
  const [values, setValues] = useState<ContactValues>(EMPTY);
  const [honeypot, setHoneypot] = useState('');
  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [status, setStatus] = useState<FormStatus>(IDLE);
  const id = (key: string) => `${uid}-${key}`;

  function update<K extends keyof ContactValues>(key: K, value: ContactValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (honeypot) return;
    const found = validate(values);
    setErrors(found);
    const first = (Object.keys(found)[0] ?? null) as FieldKey | null;
    if (first) {
      document.getElementById(id(first))?.focus();
      setStatus({ state: 'error', message: 'Please fix the highlighted fields.' });
      return;
    }
    if (!CONTACT_PATH) {
      setStatus({
        state: 'error',
        message: `The contact form is not connected yet. Email ${SALES_EMAIL} instead.`,
      });
      return;
    }
    setStatus({ state: 'loading', message: 'Sending…' });
    try {
      await submitForm(CONTACT_PATH, { ...values, source: window.location.pathname });
      setValues(EMPTY);
      setErrors({});
      setStatus({
        state: 'success',
        message: 'Thanks. A member of the team will reply within one business day.',
      });
    } catch {
      setStatus({
        state: 'error',
        message: 'We could not send your message. Please try again, or email us directly.',
      });
    }
  }

  const statusTone =
    status.state === 'success'
      ? 'text-accent'
      : status.state === 'error'
        ? 'text-severityText-critical'
        : 'text-muted';

  return (
    <MarketingLayout
      title="Contact | AEGIS Threat Detection"
      description="Talk to the AEGIS team about a demo, a deployment or support. Find our offices in Hyderabad, London, Singapore and Austin."
    >
      <PageHero
        crumb="Contact"
        title="Talk to the team that builds the detection engine"
        lead="Book a demo, ask about deployment, or report a security issue. Engineers answer the questions that matter."
      />

      <section
        aria-labelledby="contact-title"
        className="mx-auto grid w-full max-w-[1200px] gap-12 px-6 pb-16 md:grid-cols-[1.1fr_0.9fr] md:px-12 md:pb-[6rem]"
      >
        <Reveal>
          <div className="rounded-card border border-line bg-surface p-6 md:p-8">
            <h2 id="contact-title" className="m-0 text-h1 font-semibold text-ink">
              Send us a message
            </h2>
            <form
              onSubmit={onSubmit}
              noValidate
              aria-describedby={id('status')}
              className="mt-6 grid gap-5"
            >
              <div className="grid gap-5 md:grid-cols-2">
                <div className="grid gap-1">
                  <label htmlFor={id('name')} className="text-body font-semibold text-ink">
                    Full name
                  </label>
                  <input
                    id={id('name')}
                    name="name"
                    autoComplete="name"
                    value={values.name}
                    onChange={(event) => update('name', event.target.value)}
                    aria-invalid={errors.name ? true : undefined}
                    aria-describedby={errors.name ? id('name-error') : undefined}
                    className={FIELD_INPUT}
                  />
                  {errors.name && (
                    <p id={id('name-error')} className={FIELD_ERROR}>
                      {errors.name}
                    </p>
                  )}
                </div>
                <div className="grid gap-1">
                  <label htmlFor={id('email')} className="text-body font-semibold text-ink">
                    Work email
                  </label>
                  <input
                    id={id('email')}
                    type="email"
                    name="email"
                    autoComplete="email"
                    value={values.email}
                    onChange={(event) => update('email', event.target.value)}
                    aria-invalid={errors.email ? true : undefined}
                    aria-describedby={errors.email ? id('email-error') : undefined}
                    className={FIELD_INPUT}
                  />
                  {errors.email && (
                    <p id={id('email-error')} className={FIELD_ERROR}>
                      {errors.email}
                    </p>
                  )}
                </div>
              </div>

              <div className="grid gap-5 md:grid-cols-2">
                <div className="grid gap-1">
                  <label htmlFor={id('company')} className="text-body font-semibold text-ink">
                    Company <span className="font-normal text-muted">(optional)</span>
                  </label>
                  <input
                    id={id('company')}
                    name="company"
                    autoComplete="organization"
                    value={values.company}
                    onChange={(event) => update('company', event.target.value)}
                    className={FIELD_INPUT}
                  />
                </div>
                <div className="grid gap-1">
                  <label htmlFor={id('topic')} className="text-body font-semibold text-ink">
                    What do you need?
                  </label>
                  <select
                    id={id('topic')}
                    name="topic"
                    value={values.topic}
                    onChange={(event) =>
                      update('topic', event.target.value as ContactValues['topic'])
                    }
                    className={FIELD_INPUT}
                  >
                    <option value="demo">Book a demo</option>
                    <option value="deploy">Deployment help</option>
                    <option value="support">Product support</option>
                    <option value="security">Report a security issue</option>
                  </select>
                </div>
              </div>

              <div className="grid gap-1">
                <label htmlFor={id('message')} className="text-body font-semibold text-ink">
                  Message
                </label>
                <textarea
                  id={id('message')}
                  name="message"
                  rows={5}
                  value={values.message}
                  onChange={(event) => update('message', event.target.value)}
                  aria-invalid={errors.message ? true : undefined}
                  aria-describedby={errors.message ? id('message-error') : undefined}
                  className={FIELD_INPUT}
                />
                {errors.message && (
                  <p id={id('message-error')} className={FIELD_ERROR}>
                    {errors.message}
                  </p>
                )}
              </div>

              <div className="grid gap-1">
                <label
                  htmlFor={id('consent')}
                  className="flex items-start gap-3 text-body-sm text-muted"
                >
                  <input
                    id={id('consent')}
                    type="checkbox"
                    name="consent"
                    checked={values.consent}
                    onChange={(event) => update('consent', event.target.checked)}
                    aria-invalid={errors.consent ? true : undefined}
                    aria-describedby={errors.consent ? id('consent-error') : undefined}
                    className="mt-1 size-icon-md shrink-0 accent-accent"
                  />
                  <span>
                    I agree that AEGIS may contact me about this request. We do not sell contact
                    details. See the privacy policy.
                  </span>
                </label>
                {errors.consent && (
                  <p id={id('consent-error')} className={FIELD_ERROR}>
                    {errors.consent}
                  </p>
                )}
              </div>

              {/* Honeypot: off-screen and removed from the accessibility tree. */}
              <div
                className="absolute -left-[10000px] h-[1px] w-[1px] overflow-hidden"
                aria-hidden="true"
              >
                <label>
                  Website
                  <input
                    type="text"
                    tabIndex={-1}
                    autoComplete="off"
                    value={honeypot}
                    onChange={(event) => setHoneypot(event.target.value)}
                  />
                </label>
              </div>

              <div>
                <button
                  type="submit"
                  disabled={status.state === 'loading'}
                  className="inline-flex items-center gap-2 rounded-pill bg-accent px-6 py-3 text-caption font-semibold uppercase tracking-widest text-onAccent transition-colors duration-micro hover:opacity-90 focus-visible:ring-2 disabled:opacity-60"
                >
                  <Send aria-hidden="true" className="size-icon-sm" />
                  Send message
                </button>
              </div>
              <p
                id={id('status')}
                role="status"
                aria-live="polite"
                className={`m-0 text-body-sm ${statusTone}`}
              >
                {status.message}
              </p>
            </form>
          </div>
        </Reveal>

        <Reveal delayMs={120}>
          <aside aria-labelledby="direct-title" className="grid gap-6">
            <div>
              <h2 id="direct-title" className="m-0 text-h1 font-semibold text-ink">
                Reach us directly
              </h2>
              <p className="mb-0 mt-3 text-body text-muted">
                Sales:{' '}
                <a href={`mailto:${SALES_EMAIL}`} className="text-accent">
                  {SALES_EMAIL}
                </a>
              </p>
              <p className="mb-0 mt-2 text-body text-muted">
                Vulnerability reports:{' '}
                <a href={`mailto:${SECURITY_EMAIL}`} className="text-accent">
                  {SECURITY_EMAIL}
                </a>
              </p>
            </div>
            <ul className="m-0 grid list-none gap-4 p-0">
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
          </aside>
        </Reveal>
      </section>

      <section aria-labelledby="map-title" className="border-t border-line bg-surface">
        <div className="mx-auto w-full max-w-[1200px] px-6 py-16 md:px-12 md:py-[6rem]">
          <Reveal>
            <p className="m-0 font-mono text-caption uppercase tracking-widest text-accent">
              Offices
            </p>
            <h2 id="map-title" className="mt-3 text-display">
              Four offices, one support queue
            </h2>
            <div className="mt-10">
              <DotMap />
            </div>
          </Reveal>
        </div>
      </section>
    </MarketingLayout>
  );
}
