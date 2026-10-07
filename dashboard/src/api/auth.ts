/** The browser-facing contracts for the password and local-setup endpoints (T-417). */
import { getJson, postJson, postVoid } from './client';
import { clearSessionToken, refreshToken, setSessionCredentials } from './session';

export interface AuthStatus {
  setup_available: boolean;
  setup_enabled: boolean;
  account_exists: boolean;
}

export interface SessionCredentials {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
  subject: string;
  role: string;
}

const PUBLIC_AUTH_OPTIONS = { includeAuth: false, retryUnauthorized: false } as const;

/** Read whether the development-only first administrator screen is available. */
export function getAuthStatus(): Promise<AuthStatus> {
  return getJson<AuthStatus>('/api/v1/auth/status', PUBLIC_AUTH_OPTIONS);
}

/** Create the first local administrator using a password chosen by the operator. */
export async function setupLocalAdmin(
  email: string,
  password: string,
): Promise<SessionCredentials> {
  const credentials = await postJson<SessionCredentials>(
    '/api/v1/auth/setup',
    { email, password },
    PUBLIC_AUTH_OPTIONS,
  );
  setSessionCredentials(credentials.access_token, credentials.refresh_token);
  return credentials;
}

/** Sign in; a 401 deliberately carries no account-existence detail. */
export async function signIn(email: string, password: string): Promise<SessionCredentials> {
  const credentials = await postJson<SessionCredentials>(
    '/api/v1/auth/login',
    { email, password },
    PUBLIC_AUTH_OPTIONS,
  );
  setSessionCredentials(credentials.access_token, credentials.refresh_token);
  return credentials;
}

/** Revoke the refresh family, then always forget the tab-scoped credentials. */
export async function signOut(): Promise<void> {
  const token = refreshToken();
  try {
    if (token !== null) {
      await postVoid('/api/v1/auth/logout', { refresh_token: token }, PUBLIC_AUTH_OPTIONS);
    }
  } finally {
    clearSessionToken();
  }
}
