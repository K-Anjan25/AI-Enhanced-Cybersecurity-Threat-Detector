/**
 * The dashboard's session credentials, in one place (T-417).
 *
 * The API is authenticated and the app now has a real password/bootstrap flow.
 * The access token and its single-use refresh token both live in `sessionStorage`,
 * never `localStorage`: they disappear with the tab, rather than remaining on a
 * shared workstation. The realtime layer reads the access token for the WebSocket
 * handshake; the HTTP client reads both so it can attach the bearer and rotate an
 * expired pair. Every access-token change is broadcast, so the socket closes and
 * reopens with the credential that now holds authority.
 *
 * This module deliberately knows nothing about HTTP. `src/api/client.ts` attaches
 * the access token and rotates the pair on a 401, keeping storage and transport
 * from depending on each other.
 */

/** Where the short-lived access token lives. */
export const SESSION_TOKEN_KEY = 'aegis.session-token';
/** Where the single-use refresh credential lives, in the same tab-scoped store. */
export const SESSION_REFRESH_TOKEN_KEY = 'aegis.session-refresh-token';

let cached: string | null = null;
let refreshCached: string | null = null;
let loaded = false;
let refreshLoaded = false;
const listeners = new Set<(token: string | null) => void>();

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    // A browser with storage disabled (private mode, an embedded webview) throws
    // on access. The dashboard then works exactly as far as the API allows it,
    // which is the honest outcome: no credential, no session.
    return null;
  }
}

function normalise(token: string | null): string | null {
  return token === null || token.trim() === '' ? null : token.trim();
}

function publishAccessToken(token: string | null): void {
  cached = token;
  loaded = true;
  const store = storage();
  if (token === null) store?.removeItem(SESSION_TOKEN_KEY);
  else store?.setItem(SESSION_TOKEN_KEY, token);
  for (const listener of listeners) listener(token);
}

function storeRefreshToken(token: string | null): void {
  refreshCached = token;
  refreshLoaded = true;
  const store = storage();
  if (token === null) store?.removeItem(SESSION_REFRESH_TOKEN_KEY);
  else store?.setItem(SESSION_REFRESH_TOKEN_KEY, token);
}

/** Set an access token without a refresh credential, and broadcast the change. */
export function setSessionToken(token: string | null): void {
  storeRefreshToken(null);
  publishAccessToken(normalise(token));
}

/** Store a freshly issued or rotated pair and notify the realtime connection. */
export function setSessionCredentials(
  accessToken: string | null,
  refreshToken: string | null,
): void {
  const access = normalise(accessToken);
  const refresh = normalise(refreshToken);
  storeRefreshToken(access === null ? null : refresh);
  publishAccessToken(access);
}

/** The current access token, or `null` when there is no session. */
export function sessionToken(): string | null {
  if (!loaded) {
    const stored = storage()?.getItem(SESSION_TOKEN_KEY) ?? '';
    cached = stored === '' ? null : stored;
    loaded = true;
  }
  return cached;
}

/** The current refresh token, or `null` when the tab has no session. */
export function refreshToken(): string | null {
  if (!refreshLoaded) {
    const stored = storage()?.getItem(SESSION_REFRESH_TOKEN_KEY) ?? '';
    refreshCached = stored === '' ? null : stored;
    refreshLoaded = true;
  }
  return refreshCached;
}

/** Forget both credentials. Whoever reacts to the access change closes the socket. */
export function clearSessionToken(): void {
  if (sessionToken() === null && refreshToken() === null) return;
  storeRefreshToken(null);
  publishAccessToken(null);
}

/**
 * Subscribe to access-token changes. Returns the unsubscribe.
 *
 * `setSessionCredentials` fires the listeners even when the bytes are unchanged:
 * a refresh is a new authority, and a socket that kept its old connection because
 * the string happened to match is not a state anyone asked for.
 */
export function onSessionTokenChange(listener: (token: string | null) => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Reset the module's state. Tests only; a running client never calls this. */
export function resetSessionForTests(): void {
  cached = null;
  refreshCached = null;
  loaded = false;
  refreshLoaded = false;
  listeners.clear();
  storage()?.removeItem(SESSION_TOKEN_KEY);
  storage()?.removeItem(SESSION_REFRESH_TOKEN_KEY);
}
