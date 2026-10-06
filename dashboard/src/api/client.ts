/**
 * The dashboard's API client.
 *
 * It lives in `src/api/` because R-23 says so — "all network access goes through a
 * typed client in `src/api/`" — and the eslint config enforces it: `fetch` is a
 * restricted global everywhere else in the dashboard. This is therefore the one
 * file allowed to reach the network, and it is also where the rules about talking
 * to the backend are written down.
 *
 * Three of them matter and none is obvious from a `fetch` call:
 *
 *   * **Relative paths, resolved against the page's own origin.** The browser must
 *     never call the backend directly (the dev server proxies `/api`, `/ws` and
 *     `/metrics`), so a path here is never an absolute URL and never a host.
 *     Resolving through `window.location.origin` keeps the *relative* form in the
 *     source while still producing a URL `fetch` accepts under jsdom, so a test
 *     exercises the same string a browser would.
 *   * **`GET` and `POST` only, and `POST` sends JSON.** That is the whole of the
 *     API this dashboard is allowed to write: a verdict (T-404). A body is
 *     serialised before the request starts, so a body that cannot be serialised
 *     fails as a bug rather than as an outage.
 *   * **Errors carry no URL and no body.** R-58 forbids putting secrets, URLs or
 *     content into messages that reach a log or a screen: a FastAPI error body
 *     echoes back part of the request, and a URL carries query parameters. The
 *     error's message says what kind of failure it was; the status is a number.
 *   * **The session token rides along, and a 401 ends the session.** The API is
 *     authenticated (T-302); the credential lives in `src/api/session.ts` and is
 *     attached here, in the one place every request is built, rather than by each
 *     caller. A `401` means the credential is not (or no longer) valid, so the
 *     session is cleared and the socket's refusal banner becomes true; a `403`
 *     does **not**, because a valid credential without the required role is a
 *     permissions message, not a reason to sign the operator out.
 *   * **Every request is abortable, and a request that hangs is aborted anyway.**
 *     React Query cancels on unmount by signal; the timeout covers the case where
 *     nothing cancels — a proxy holding the socket open forever, which would leave
 *     a panel loading longer than the data could possibly still be useful.
 */

import { clearSessionToken, sessionToken } from './session';

/** What kind of failure happened, which is what the UI is allowed to say. */
export type ApiFailure = 'unreachable' | 'timeout' | 'status' | 'malformed';

export class ApiError extends Error {
  /** The HTTP status, or `null` when no response arrived. */
  readonly status: number | null;

  readonly failure: ApiFailure;

  constructor(failure: ApiFailure, status: number | null, message: string) {
    super(message);
    this.name = 'ApiError';
    this.failure = failure;
    this.status = status;
  }
}

/** How long a request may take before it is abandoned. */
export const REQUEST_TIMEOUT_MS = 10_000;

interface RequestOptions {
  signal?: AbortSignal | undefined;
  timeoutMs?: number;
  accept?: string;
  /** Defaults to `GET`. Nothing here needs a method the API does not serve. */
  method?: 'GET' | 'POST';
  /** Serialised as JSON. Only meaningful with `POST`. */
  body?: unknown;
  /**
   * Statuses whose body is still the answer.
   *
   * `/readyz` is the reason this exists: it reports "not ready" as HTTP 503 *with
   * a body naming the dependency that is down*. Treating that as a failure would
   * throw away the only part an operator needs.
   */
  okStatuses?: readonly number[];
}

/**
 * Absolutely-URL a path without ever inventing a host.
 *
 * The path must be one of the proxied prefixes; anything else is a programming
 * error and is refused here rather than at the network, because a cross-origin
 * call would be blocked by the browser and look like an outage.
 */
function resolve(path: string): string {
  if (!path.startsWith('/')) {
    throw new Error('api paths must be absolute paths on this origin');
  }
  return new URL(path, window.location.origin).toString();
}

/**
 * One request, with both cancellation routes wired to one controller.
 *
 * The caller's signal and the timeout share a controller, so an abort is an abort
 * either way, and the listener is removed on every exit path — a listener left on
 * a signal that outlives the request (React Query reuses signals) would abort a
 * later request for a reason that no longer applies.
 */
async function request(path: string, options: RequestOptions): Promise<Response> {
  const controller = new AbortController();
  const {
    signal,
    timeoutMs = REQUEST_TIMEOUT_MS,
    accept,
    okStatuses = [],
    method = 'GET',
    body,
  } = options;
  let timedOut = false;

  const onAbort = () => controller.abort();
  if (signal !== undefined) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', onAbort, { once: true });
  }
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  let url: string;
  let payload: string | undefined;
  try {
    // Resolved and serialised before the network call and outside its error
    // handling: a bad path or an unserialisable body is a programming error and
    // must surface as one, not as an outage.
    url = resolve(path);
    payload = body === undefined ? undefined : JSON.stringify(body);
  } catch (error) {
    clearTimeout(timer);
    throw error;
  }
  const headers: Record<string, string> = { accept: accept ?? 'application/json' };
  if (payload !== undefined) headers['content-type'] = 'application/json';
  const token = sessionToken();
  // No token means no header, not an empty one: `Authorization: Bearer ` is a
  // credential-shaped string that the API would have to reject, and it reads in a
  // log like an attempt rather than an absence.
  if (token !== null) headers['authorization'] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(url, {
      // The API answers JSON; asking for it stops an HTML error page being
      // parsed as data and reported as a malformed response.
      method,
      signal: controller.signal,
      headers,
      ...(payload === undefined ? {} : { body: payload }),
    });
  } catch {
    // Only a transport failure reaches here; a refusal by the API is handled
    // below, where it stays a refusal rather than becoming "unreachable".
    if (timedOut)
      throw new ApiError('timeout', null, `the request took longer than ${timeoutMs} ms`);
    throw new ApiError('unreachable', null, 'the service could not be reached');
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }

  if (!response.ok && !okStatuses.includes(response.status)) throw statusError(response);
  return response;
}

/** A status the API refused with — the status is data, the body is not. */
function statusError(response: Response): ApiError {
  // 401 only. See the module docstring: a 403 is an authorisation answer about a
  // credential that is still good, and signing the operator out over it would
  // turn "you may not record verdicts" into "you are not signed in".
  if (response.status === 401) clearSessionToken();
  return new ApiError('status', response.status, `the service answered ${response.status}`);
}

/** Read a response as JSON, or report that it was not. */
async function readJson<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError('malformed', response.status, 'the response was not JSON');
  }
}

/** `GET` a JSON document. */
export async function getJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return readJson<T>(await request(path, options));
}

/**
 * `POST` a JSON body and read a JSON answer.
 *
 * The body is serialised in `request`, before the network call, so an object that
 * cannot be serialised throws a programming error rather than being reported as
 * "the service could not be reached".
 */
export async function postJson<T>(
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<T> {
  return readJson<T>(await request(path, { ...options, method: 'POST', body }));
}

/** `GET` a text document, for `/metrics`' exposition format. */
export async function getText(path: string, options: RequestOptions = {}): Promise<string> {
  const response = await request(path, { ...options, accept: 'text/plain' });
  try {
    return await response.text();
  } catch {
    throw new ApiError('malformed', response.status, 'the response body could not be read');
  }
}

/** Build a query string, dropping absent values. */
export function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded === '' ? '' : `?${encoded}`;
}
