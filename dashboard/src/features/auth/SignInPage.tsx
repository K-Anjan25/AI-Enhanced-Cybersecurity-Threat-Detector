import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import { ApiError } from '../../api/client';
import { getAuthStatus, signIn, setupLocalAdmin } from '../../api/auth';
import { Button, Spinner } from '../../components/ui';
import { useTheme } from '../../theme/ThemeProvider';
import { AegisLogo } from '../../components/brand/AegisLogo';

export function SignInPage() {
  const { theme, toggleTheme } = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const status = useQuery({
    queryKey: ['auth', 'status'],
    queryFn: getAuthStatus,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  const setupAvailable = status.data?.setup_available === true;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (setupAvailable && password !== confirmation) {
      setError('The passwords do not match.');
      return;
    }
    setPending(true);
    try {
      if (setupAvailable) await setupLocalAdmin(email, password);
      else await signIn(email, password);
    } catch (caught) {
      setError(authErrorMessage(caught, setupAvailable));
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col bg-base text-ink">
      <header className="flex h-topbar items-center justify-between px-6">
        <Link to="/" className="flex items-center gap-2 text-h2 uppercase tracking-widest">
          <AegisLogo />
          AEGIS
        </Link>
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          className="rounded-input border border-line px-3 py-1 text-body-sm font-semibold text-muted hover:text-ink"
        >
          {theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
        </button>
      </header>

      <section className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm rounded-card border border-line bg-surface p-8">
          <h1 className="text-h1">{setupAvailable ? 'Create administrator' : 'Sign in'}</h1>

          {status.isPending ? (
            <div className="mt-6 flex items-center gap-3 text-body-sm text-muted">
              <Spinner />
              Checking account setup…
            </div>
          ) : status.isError ? (
            <p className="mt-6 text-body-sm text-severityText-high" role="status">
              Authentication service unreachable.
            </p>
          ) : null}

          <form className="mt-6 grid gap-4" onSubmit={submit}>
            <div>
              <label className="text-caption font-semibold text-ink" htmlFor="auth-email">
                Email address
              </label>
              <input
                id="auth-email"
                autoComplete="username"
                type="email"
                required
                maxLength={254}
                value={email}
                onChange={(event) => setEmail(event.currentTarget.value)}
                className="mt-2 h-row-comfortable w-full rounded-input border border-line bg-base px-3 text-body text-ink"
              />
            </div>
            <div>
              <label className="text-caption font-semibold text-ink" htmlFor="auth-password">
                Password
              </label>
              <input
                id="auth-password"
                autoComplete={setupAvailable ? 'new-password' : 'current-password'}
                type="password"
                required
                minLength={12}
                maxLength={256}
                value={password}
                onChange={(event) => setPassword(event.currentTarget.value)}
                className="mt-2 h-row-comfortable w-full rounded-input border border-line bg-base px-3 text-body text-ink"
              />
            </div>
            {setupAvailable ? (
              <div>
                <label className="text-caption font-semibold text-ink" htmlFor="auth-confirm">
                  Confirm password
                </label>
                <input
                  id="auth-confirm"
                  autoComplete="new-password"
                  type="password"
                  required
                  minLength={12}
                  maxLength={256}
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.currentTarget.value)}
                  className="mt-2 h-row-comfortable w-full rounded-input border border-line bg-base px-3 text-body text-ink"
                />
              </div>
            ) : null}

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
              {setupAvailable ? 'Create administrator' : 'Sign in'}
              <ArrowRight aria-hidden="true" className="size-icon-sm" />
            </Button>
          </form>
        </div>
      </section>
    </main>
  );
}

function authErrorMessage(error: unknown, setup: boolean): string {
  if (error instanceof ApiError) {
    if (error.status === 401)
      return 'Email or password is incorrect. Check your details and try again.';
    if (error.status === 409)
      return 'An administrator has already been created. Sign in with that account.';
    if (error.status === 404 && setup) {
      return 'Local setup is disabled by the backend. Enable it only for a private development instance.';
    }
    if (error.failure === 'unreachable' || error.failure === 'timeout') {
      return 'Authentication service unreachable.';
    }
    return `Authentication was refused (HTTP ${error.status ?? 'unknown'}).`;
  }
  return 'Authentication failed. Try again; if the problem continues, check the backend logs.';
}
