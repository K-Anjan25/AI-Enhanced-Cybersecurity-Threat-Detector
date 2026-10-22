import { useId, useState, type FormEvent } from 'react';
import { Send } from 'lucide-react';
import { SALES_EMAIL } from '../content';
import { IDLE, NEWSLETTER_PATH, isEmail, submitForm, type FormStatus } from './forms';

/**
 * Newsletter sign-up. Validates the address, drops submissions that fill the hidden
 * honeypot field, reports progress in a polite live region, and never claims success
 * without a server response.
 */
export function NewsletterForm({ variant = 'band' }: { variant?: 'band' | 'footer' }) {
  const uid = useId();
  const [email, setEmail] = useState('');
  const [honeypot, setHoneypot] = useState('');
  const [error, setError] = useState('');
  const [status, setStatus] = useState<FormStatus>(IDLE);
  const inputId = `${uid}-email`;
  const statusId = `${uid}-status`;
  const errorId = `${uid}-error`;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (honeypot) return; // bots fill hidden fields; humans never see them
    if (!isEmail(email)) {
      setError('Enter a valid work email, for example name@company.com.');
      setStatus(IDLE);
      return;
    }
    setError('');
    if (!NEWSLETTER_PATH) {
      setStatus({
        state: 'error',
        message: `Newsletter sign-up is not connected yet. Email ${SALES_EMAIL} instead.`,
      });
      return;
    }
    setStatus({ state: 'loading', message: 'Subscribing…' });
    try {
      await submitForm(NEWSLETTER_PATH, { email: email.trim(), source: window.location.pathname });
      setEmail('');
      setStatus({
        state: 'success',
        message: 'Thanks. Check your inbox to confirm your subscription.',
      });
    } catch {
      setStatus({
        state: 'error',
        message: 'We could not subscribe you right now. Please try again shortly.',
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
    <form
      onSubmit={onSubmit}
      noValidate
      aria-describedby={statusId}
      className={`flex flex-wrap gap-3 ${variant === 'footer' ? '' : 'items-start'}`}
    >
      <div className="flex min-w-[240px] flex-1 flex-col gap-1">
        <label htmlFor={inputId} className="sr-only">
          Work email address
        </label>
        <input
          id={inputId}
          type="email"
          name="email"
          autoComplete="email"
          placeholder="you@company.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          required
          className="min-h-12 w-full rounded-input border border-line bg-base px-4 py-3 text-body text-ink placeholder:text-muted focus-visible:ring-2"
        />
        {error && (
          <p id={errorId} className="m-0 text-body-sm text-severityText-critical">
            {error}
          </p>
        )}
      </div>

      {/* Honeypot: off-screen and removed from the accessibility tree. */}
      <div className="absolute -left-[10000px] h-[1px] w-[1px] overflow-hidden" aria-hidden="true">
        <label>
          Leave this field empty
          <input
            type="text"
            name="website"
            tabIndex={-1}
            autoComplete="off"
            value={honeypot}
            onChange={(event) => setHoneypot(event.target.value)}
          />
        </label>
      </div>

      <button
        type="submit"
        disabled={status.state === 'loading'}
        className="inline-flex min-h-12 items-center gap-2 rounded-pill bg-accent px-6 py-3 text-caption font-semibold uppercase tracking-widest text-onAccent transition-colors duration-micro hover:opacity-90 focus-visible:ring-2 disabled:opacity-60"
      >
        <Send aria-hidden="true" className="size-icon-sm" />
        Subscribe
      </button>

      <p
        id={statusId}
        role="status"
        aria-live="polite"
        className={`m-0 w-full text-body-sm ${statusTone}`}
      >
        {status.message}
      </p>
    </form>
  );
}
