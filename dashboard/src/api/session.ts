/**
 * The dashboard's session credential, in one place.
 *
 * The API is authenticated (`POST /auth/login`, T-302) and until now nothing in
 * the dashboard held a token — the overview reads `/metrics` (unauthenticated, so
 * a status page needs no credential) and the alert screens were built against a
 * development proxy that made 401s somebody else's problem. The realtime layer
 * cannot work that way: a WebSocket handshake carries the token in
 * `Sec-WebSocket-Protocol` (`aegis.bearer.<token>`, T-310) and the polling
 * fallback needs the same credential as a header, so the token has to live
 * somewhere both can read and both can be told about.
 *
 * Three decisions, each of them small and each of them a rule:
 *
 *   * **`sessionStorage`, not `localStorage`.** A bearer token that outlives the
 *     tab is a token left on a shared workstation at the end of the day. The theme
 *     preference uses `localStorage` precisely because it is *not* a credential.
 *   * **A change is broadcast.** A credential that appears (sign-in, T-417),
 *     rotates, or is cleared must reopen the socket rather than wait for the next
 *     backoff step: a connection's authority is the token it was opened with, and
 *     nothing else can fix a refused handshake.
 *   * **No token is a valid state, and it is said out loud.** The client opens the
 *     socket without a credential, the server refuses with 4401, and the banner
 *     says the session is not authenticated — which is more useful than a spinner
 *     that never resolves. The sign-in screen itself is T-417.
 *
 * This module deliberately knows nothing about HTTP. `src/api/client.ts` reads the
 * token to attach it and clears it on a 401, which is where the status code is;
 * importing the other way would be a cycle between the two modules that both need
 * to be simple.
 */

/** Where the token lives. Session-scoped on purpose — see the module docstring. */
export const SESSION_TOKEN_KEY = 'aegis.session-token';

let cached: string | null = null;
let loaded = false;
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

/** Set the session token, and tell everything that holds a connection. */
export function setSessionToken(token: string | null): void {
  const normalised = token === null || token.trim() === '' ? null : token.trim();
  cached = normalised;
  loaded = true;
  storage()?.setItem(SESSION_TOKEN_KEY, normalised ?? '');
  for (const listener of listeners) listener(normalised);
}

/** The current token, or `null` when there is no session. */
export function sessionToken(): string | null {
  if (!loaded) {
    const stored = storage()?.getItem(SESSION_TOKEN_KEY) ?? '';
    cached = stored === '' ? null : stored;
    loaded = true;
  }
  return cached;
}

/** Forget the session. Whoever reacts to the change is what closes the socket. */
export function clearSessionToken(): void {
  if (sessionToken() === null) return;
  setSessionToken(null);
}

/**
 * Subscribe to token changes. Returns the unsubscribe.
 *
 * `setSessionToken` fires the listeners even when the bytes are unchanged:
 * revoking and reissuing a credential produces the same string only by accident,
 * and a socket that kept its old authority because the string matched is not a
 * state anyone asked for.
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
  loaded = false;
  listeners.clear();
  storage()?.removeItem(SESSION_TOKEN_KEY);
}
