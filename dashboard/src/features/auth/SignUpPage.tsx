import { useState, type FormEvent } from 'react';
import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import { ApiError } from '../../api/client';
import { signUp } from '../../api/auth';
import { Button } from '../../components/ui';
import { AegisLogo } from '../../components/brand/AegisLogo';

/** Self-service sign-up. The backend creates viewer accounts only, and only when enabled. */
export function SignUpPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (password !== confirmation) {
      setError('The passwords do not match.');
      return;
    }
    setPending(true);
    try {
      const reply = await signUp(email, password);
      setMessage(reply.message);
    } catch (caught) {
      setError(signUpErrorMessage(caught));
    } finally {
      setPending(false);
    }
  }

  const inputClass =
    'mt-2 h-row-comfortable w-full rounded-input border border-line bg-base px-3 text-body text-ink';

  return (
    <main className="flex min-h-screen flex-col bg-base text-ink">
      <header className="flex h-topbar items-center justify-between px-6">
        <Link to="/" className="flex items-center gap-2 text-h2 uppercase tracking-widest">
          <AegisLogo />
          AEGIS
        </Link>
      </header>

      <section className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm rounded-card border border-line bg-surface p-8">
          <h1 className="text-h1">Create an account</h1>
          <p className="mt-2 text-body-sm text-muted">
            New accounts can view dashboards. An administrator can grant more access.
          </p>

          {message !== null ? (
            <div className="mt-6 grid gap-4">
              <p className="text-body-sm text-ink" role="status">
                {message}
              </p>
              <Link to="/sign-in" className="text-body-sm font-semibold text-accent">
                Go to sign in
              </Link>
            </div>
          ) : (
            <form className="mt-6 grid gap-4" onSubmit={submit}>
              <div>
                <label className="text-caption font-semibold text-ink" htmlFor="signup-email">
                  Email address
                </label>
                <input
                  id="signup-email"
                  autoComplete="username"
                  type="email"
                  required
                  maxLength={254}
                  value={email}
                  onChange={(event) => setEmail(event.currentTarget.value)}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="text-caption font-semibold text-ink" htmlFor="signup-password">
                  Password
                </label>
                <input
                  id="signup-password"
                  autoComplete="new-password"
                  type="password"
                  required
                  minLength={12}
                  maxLength={256}
                  value={password}
                  onChange={(event) => setPassword(event.currentTarget.value)}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="text-caption font-semibold text-ink" htmlFor="signup-confirm">
                  Confirm password
                </label>
                <input
                  id="signup-confirm"
                  autoComplete="new-password"
                  type="password"
                  required
                  minLength={12}
                  maxLength={256}
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.currentTarget.value)}
                  className={inputClass}
                />
              </div>

              {error === null ? null : (
                <p className="text-body-sm text-severityText-critical" role="alert">
                  {error}
                </p>
              )}

              <Button
                type="submit"
                loading={pending}
                className="mt-2 h-row-comfortable w-full justify-center"
              >
                Create account
                <ArrowRight aria-hidden="true" className="size-icon-sm" />
              </Button>
              <Link to="/sign-in" className="text-center text-body-sm text-muted hover:text-ink">
                Already have an account? Sign in
              </Link>
            </form>
          )}
        </div>
      </section>
    </main>
  );
}

function signUpErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return 'Sign-up is turned off on this deployment.';
    if (error.status === 429) return 'Too many attempts. Wait a few minutes and try again.';
    if (error.status === 422)
      return 'Check the email address and use a password of at least 12 characters.';
    if (error.failure === 'unreachable' || error.failure === 'timeout') {
      return 'Authentication service unreachable.';
    }
    return `Sign-up was refused (HTTP ${error.status ?? 'unknown'}).`;
  }
  return 'Sign-up failed. Try again.';
}
