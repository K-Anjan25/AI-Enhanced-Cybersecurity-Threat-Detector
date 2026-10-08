import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Fingerprint, KeyRound, ShieldCheck, UserPlus } from 'lucide-react';

import { ApiError } from '../../api/client';
import { getAuthStatus, signIn, signUp, setupLocalAdmin } from '../../api/auth';
import { Button, Spinner } from '../../components/ui';
import { useTheme } from '../../theme/ThemeProvider';

type AuthMode = 'setup' | 'signin' | 'signup';

export function SignInPage() {
  const { theme, toggleTheme } = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [view, setView] = useState<'signin' | 'signup'>('signin');
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
  const signupAvailable = status.data?.account_exists === true && !setupAvailable;
  // The server's answers win over the local view: setup is forced while it is
  // offered, and the signup view only renders while registration is open.
  const mode: AuthMode = setupAvailable
    ? 'setup'
    : view === 'signup' && signupAvailable
      ? 'signup'
      : 'signin';
  const needsConfirmation = mode !== 'signin';
  const showSwitch = mode === 'signup' || signupAvailable;

  function show(next: 'signin' | 'signup') {
    setView(next);
    setError(null);
    setPassword('');
    setConfirmation('');
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (needsConfirmation && password !== confirmation) {
      setError('The passwords do not match.');
      return;
    }
    setPending(true);
    try {
      if (mode === 'setup') await setupLocalAdmin(email, password);
      else if (mode === 'signup') await signUp(email, password);
      else await signIn(email, password);
    } catch (caught) {
      setError(authErrorMessage(caught, mode));
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="relative flex min-h-screen bg-base text-ink">
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        className="absolute right-6 top-6 z-10 rounded-input border border-line bg-surface px-3 py-2 text-caption text-muted transition-colors hover:text-ink"
      >
        {theme === 'dark' ? 'Light theme' : 'Dark theme'}
      </button>

      <section className="hidden w-1/2 flex-col justify-between border-r border-line bg-surface p-8 xl:flex">
        <div className="flex items-center gap-3">
          <span className="flex size-12 items-center justify-center rounded-card bg-accent text-onAccent">
            <ShieldCheck aria-hidden="true" className="h-6 w-6" />
          </span>
          <div>
            <p className="text-h2 tracking-wide">AEGIS</p>
            <p className="text-caption uppercase tracking-wider text-muted">Security operations</p>
          </div>
        </div>

        <div className="max-w-xl">
          <span className="inline-flex items-center gap-2 rounded-pill border border-line bg-base px-3 py-2 text-caption text-accent">
            <Fingerprint aria-hidden="true" className="size-icon-sm" />
            AI-enhanced threat detection
          </span>
          <h1 className="mt-6 text-display leading-tight">Clarity in every security decision.</h1>
          <p className="mt-4 max-w-xl text-body text-muted">
            Investigate activity, understand model evidence, and take governed action from one
            focused operations console.
          </p>

          <ul className="mt-8 grid gap-3">
            <li className="flex items-start gap-3 rounded-card border border-line bg-base p-4">
              <span className="mt-1 h-2 w-2 rounded-pill bg-severity-benign" aria-hidden="true" />
              <span>
                <span className="block text-body font-semibold">Evidence stays explicit</span>
                <span className="mt-1 block text-body-sm text-muted">
                  Recorded model evaluations are shown as recorded; missing evidence stays
                  unavailable.
                </span>
              </span>
            </li>
            <li className="flex items-start gap-3 rounded-card border border-line bg-base p-4">
              <span className="mt-1 h-2 w-2 rounded-pill bg-accent" aria-hidden="true" />
              <span>
                <span className="block text-body font-semibold">
                  Access is enforced server-side
                </span>
                <span className="mt-1 block text-body-sm text-muted">
                  Roles govern protected operations, not just what the interface displays.
                </span>
              </span>
            </li>
          </ul>
        </div>

        <p className="font-mono text-caption text-muted">AEGIS / ACCESS CONTROL</p>
      </section>

      <section className="flex min-w-0 flex-1 items-center justify-center px-4 py-16 md:px-8">
        <div className="w-full max-w-md overflow-hidden rounded-modal border border-line bg-surface shadow-overlay">
          <div className="h-1 bg-accent" />
          <div className="p-6 md:p-8">
            <div className="mb-6 flex size-11 items-center justify-center rounded-card border border-line bg-base text-accent xl:hidden">
              <ShieldCheck aria-hidden="true" className="h-6 w-6" />
            </div>
            <p className="text-caption font-semibold uppercase tracking-wider text-accent">
              AEGIS / Secure workspace
            </p>
            <h2 className="mt-2 text-h1">
              {mode === 'setup'
                ? 'Create your administrator account'
                : mode === 'signup'
                  ? 'Create your account'
                  : 'Sign in to AEGIS'}
            </h2>
            <p className="mt-2 text-body-sm text-muted">
              {mode === 'setup'
                ? 'Set up the first local administrator with a password you choose.'
                : mode === 'signup'
                  ? 'Register with your work email. New accounts start with read-only access; an administrator grants roles.'
                  : 'Use your provisioned operator account to continue.'}
            </p>

            {status.isPending ? (
              <div className="mt-6 flex items-center gap-3 rounded-card border border-line bg-base p-4 text-body-sm text-muted">
                <Spinner />
                Checking account setup…
              </div>
            ) : status.isError ? (
              <div
                className="mt-6 rounded-card border border-line bg-base p-4 text-body-sm text-severityText-high"
                role="status"
              >
                The authentication service could not be reached. Check that the backend is running
                and the dashboard API proxy is connected.
              </div>
            ) : mode === 'setup' ? (
              <div className="mt-6 rounded-card border border-line bg-base p-4 text-body-sm text-severityText-high">
                The first account receives administrator permissions. Local setup is
                development-only; this account is held in memory and is cleared when the backend
                restarts.
              </div>
            ) : mode === 'signin' && status.data?.account_exists === false ? (
              <div className="mt-6 rounded-card border border-line bg-base p-4 text-body-sm text-muted">
                No account is provisioned. For a private local development instance, enable
                <code className="mx-1 rounded-input border border-line px-1 py-0.5 font-mono text-caption text-ink">
                  AEGIS_DEV_AUTH_SETUP_ENABLED=true
                </code>
                and restart the backend, or configure bootstrap credentials through your secret
                manager.
              </div>
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
                  autoComplete={needsConfirmation ? 'new-password' : 'current-password'}
                  type="password"
                  required
                  minLength={12}
                  maxLength={256}
                  value={password}
                  onChange={(event) => setPassword(event.currentTarget.value)}
                  className="mt-2 h-row-comfortable w-full rounded-input border border-line bg-base px-3 text-body text-ink"
                />
                {needsConfirmation ? (
                  <p className="mt-2 text-caption text-muted">Use at least 12 characters.</p>
                ) : null}
              </div>
              {needsConfirmation ? (
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
                <p
                  className="rounded-card border border-line bg-base p-3 text-body-sm text-severityText-critical"
                  role="alert"
                >
                  {error}
                </p>
              )}

              <Button
                type="submit"
                loading={pending}
                className="mt-2 h-row-comfortable w-full justify-center"
              >
                {mode === 'setup'
                  ? 'Create administrator'
                  : mode === 'signup'
                    ? 'Create account'
                    : 'Sign in'}
                <ArrowRight aria-hidden="true" className="size-icon-sm" />
              </Button>
            </form>

            {showSwitch ? (
              <div className="mt-6 flex items-center justify-center gap-2 border-t border-line pt-4 text-caption text-muted">
                {mode === 'signup' ? (
                  <>
                    <span>Already have an account?</span>
                    <button
                      type="button"
                      onClick={() => show('signin')}
                      className="font-semibold text-accent underline-offset-2 hover:underline"
                    >
                      Sign in
                    </button>
                  </>
                ) : (
                  <>
                    <UserPlus aria-hidden="true" className="size-icon-sm" />
                    <span>New to AEGIS?</span>
                    <button
                      type="button"
                      onClick={() => show('signup')}
                      className="font-semibold text-accent underline-offset-2 hover:underline"
                    >
                      Create an account
                    </button>
                  </>
                )}
              </div>
            ) : null}

            <div
              className={`flex items-center justify-center gap-2 text-caption text-muted ${
                showSwitch ? 'mt-4' : 'mt-6 border-t border-line pt-4'
              }`}
            >
              <KeyRound aria-hidden="true" className="size-icon-sm" />
              Passwords are protected with Argon2id; tokens stay in this tab.
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

function authErrorMessage(error: unknown, mode: AuthMode): string {
  if (error instanceof ApiError) {
    if (error.status === 401)
      return 'Email or password is incorrect. Check your details and try again.';
    if (error.status === 409) {
      // The signup link only renders while registration is open, so a 409 here
      // is the duplicate-address refusal rather than the pre-bootstrap one.
      if (mode === 'signup')
        return 'An account with that email already exists. Sign in with it instead.';
      return 'An administrator has already been created. Sign in with that account.';
    }
    if (error.status === 404 && mode === 'setup') {
      return 'Local setup is disabled by the backend. Enable it only for a private development instance.';
    }
    if (error.failure === 'unreachable' || error.failure === 'timeout') {
      return 'The authentication service could not be reached. Check the backend and dashboard proxy.';
    }
    return `Authentication was refused (HTTP ${error.status ?? 'unknown'}).`;
  }
  return 'Authentication failed. Try again; if the problem continues, check the backend logs.';
}
