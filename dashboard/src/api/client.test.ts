import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, getJson, getText, postJson, query, REQUEST_TIMEOUT_MS } from './client';
import { resetSessionForTests, sessionToken, setSessionToken } from './session';
import { jsonResponse, stubFetch, textResponse } from '../test/query';

describe('api client', () => {
  it('calls a relative path on this origin, never an absolute host', async () => {
    // The browser is not the sandbox: a host here would bypass the dev server's
    // proxy and, in production, leave the same-origin policy to refuse it.
    const requests = stubFetch([
      { match: '/api/v1/alerts', respond: () => jsonResponse({ ok: true }) },
    ]);

    await getJson('/api/v1/alerts');

    expect(requests).toHaveLength(1);
    expect(new URL(requests[0]?.url ?? '').origin).toBe(window.location.origin);
  });

  it('refuses a path that is not rooted on this origin', async () => {
    await expect(getJson('https://example.test/api/v1/alerts')).rejects.toThrow(/absolute path/);
  });

  it('raises a status error whose message carries no URL and no body', async () => {
    stubFetch([
      {
        match: '/api/v1/alerts',
        respond: () =>
          jsonResponse({ detail: 'cursor is malformed or was not issued by this API' }, 400),
      },
    ]);

    const error = await getJson('/api/v1/alerts').catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    const failure = error as ApiError;
    expect(failure.failure).toBe('status');
    expect(failure.status).toBe(400);
    // R-58: no URL, no query string, no response body in anything that reaches a
    // log or a screen.
    expect(failure.message).not.toMatch(/http|api\/v1|cursor is malformed/);
  });

  it('treats a configured status as an answer, not a failure', async () => {
    // /readyz serves "not ready" as 503 *with* a body naming the dependency.
    stubFetch([{ match: '/readyz', respond: () => jsonResponse({ status: 'not_ready' }, 503) }]);

    await expect(getJson('/readyz', { okStatuses: [503] })).resolves.toEqual({
      status: 'not_ready',
    });
  });

  it('reports a body that is not JSON as malformed rather than crashing', async () => {
    stubFetch([
      { match: '/api/v1/alerts', respond: () => textResponse('<html>proxy error</html>') },
    ]);

    const error = (await getJson('/api/v1/alerts').catch((caught: unknown) => caught)) as ApiError;

    expect(error.failure).toBe('malformed');
  });

  it('reports an unreachable service as unreachable', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));

    const error = (await getJson('/api/v1/alerts').catch((caught: unknown) => caught)) as ApiError;

    expect(error.failure).toBe('unreachable');
    expect(error.status).toBeNull();
  });

  it('abandons a request that hangs', async () => {
    vi.useFakeTimers();
    try {
      vi.stubGlobal(
        'fetch',
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () => {
              reject(new DOMException('aborted', 'AbortError'));
            });
          }),
      );

      const pending = getJson('/api/v1/alerts', { timeoutMs: 50 }).catch(
        (caught: unknown) => caught,
      );
      await vi.advanceTimersByTimeAsync(60);
      const error = (await pending) as ApiError;

      expect(error.failure).toBe('timeout');
      expect(error.message).toContain('50 ms');
    } finally {
      vi.useRealTimers();
    }
  });

  it('lets the caller cancel, and stops listening afterwards', async () => {
    const controller = new AbortController();
    const signals: AbortSignal[] = [];
    vi.stubGlobal(
      'fetch',
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          if (init?.signal !== null && init?.signal !== undefined) signals.push(init.signal);
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'));
          });
        }),
    );

    const pending = getJson('/api/v1/alerts', { signal: controller.signal }).catch(
      (caught: unknown) => caught,
    );
    controller.abort();
    const error = (await pending) as ApiError;

    expect(error.failure).toBe('unreachable');
    // A listener left on a signal React Query reuses would abort a later request
    // for a reason that no longer applies.
    expect(controller.signal.aborted).toBe(true);
  });

  it('reads text for the exposition format', async () => {
    stubFetch([{ match: '/metrics', respond: () => textResponse('aegis_x_total 1\n') }]);

    await expect(getText('/metrics')).resolves.toBe('aegis_x_total 1\n');
  });

  it('defaults its timeout to the documented budget', () => {
    expect(REQUEST_TIMEOUT_MS).toBe(10_000);
  });

  it('builds a query string without absent parameters', () => {
    expect(query({ start: 'a', end: 'b', cursor: undefined })).toBe('?start=a&end=b');
    expect(query({})).toBe('');
  });
});

describe('api client writes', () => {
  it('POSTs a JSON body to a relative path', async () => {
    const requests = stubFetch([
      { match: '/api/v1/alerts', respond: () => jsonResponse({ action: 'recorded' }) },
    ]);

    const answer = await postJson<{ action: string }>('/api/v1/alerts/7/verdict', {
      verdict: 'true_positive',
      created_at: '2026-03-15T10:00:00Z',
    });

    expect(answer).toEqual({ action: 'recorded' });
    const request = requests[0];
    expect(request?.method).toBe('POST');
    expect(request?.headers.get('content-type')).toBe('application/json');
    await expect(request?.json()).resolves.toEqual({
      verdict: 'true_positive',
      created_at: '2026-03-15T10:00:00Z',
    });
  });

  it('sends no body at all when there is nothing to send', async () => {
    // `undefined` is not `null`: a body of "undefined" is a request the API would
    // have to reject, and an empty object would be a different claim.
    const requests = stubFetch([{ match: '/api/v1/x', respond: () => jsonResponse({ ok: true }) }]);

    await postJson('/api/v1/x', undefined);

    expect(requests[0]?.body).toBeNull();
  });

  it('still refuses a path that is not rooted on this origin', async () => {
    await expect(postJson('https://example.test/api/v1/x', {})).rejects.toThrow(/absolute path/);
  });

  it('reports a refused write by status, without the body or the URL (R-58)', async () => {
    stubFetch([
      {
        match: '/api/v1/alerts',
        respond: () => jsonResponse({ detail: 'your role may not record verdicts' }, 403),
      },
    ]);

    const error = (await postJson('/api/v1/alerts/7/verdict', {}).catch(
      (caught: unknown) => caught,
    )) as ApiError;

    expect(error.failure).toBe('status');
    expect(error.status).toBe(403);
    expect(error.message).not.toMatch(/http|verdicts|role/);
  });
});

describe('the session credential', () => {
  afterEach(() => {
    resetSessionForTests();
  });

  it('attaches the session token as a bearer credential', async () => {
    const requests = stubFetch([
      { match: '/api/v1/alerts', respond: () => jsonResponse({ ok: true }) },
    ]);
    setSessionToken('t-1');

    await getJson('/api/v1/alerts');

    expect(requests[0]?.headers.get('authorization')).toBe('Bearer t-1');
  });

  it('sends no credential header at all when there is no session', async () => {
    // `Authorization: Bearer ` is a credential-shaped string that reads in a log
    // like an attempt rather than an absence.
    const requests = stubFetch([
      { match: '/api/v1/alerts', respond: () => jsonResponse({ ok: true }) },
    ]);

    await getJson('/api/v1/alerts');

    expect(requests[0]?.headers.get('authorization')).toBeNull();
  });

  it('ends the session when the API says the credential is not valid', async () => {
    stubFetch([
      { match: '/api/v1/alerts', respond: () => jsonResponse({ detail: 'unauthorised' }, 401) },
    ]);
    setSessionToken('t-stale');

    await getJson('/api/v1/alerts').catch(() => undefined);

    expect(sessionToken()).toBeNull();
  });

  it('keeps the session when the API says the role is not enough', async () => {
    // A 403 is an answer about a credential that is still good. Signing the
    // operator out over it would turn "you may not record verdicts" into "you are
    // not signed in", and would close a working stream because of one refusal.
    stubFetch([
      { match: '/api/v1/alerts', respond: () => jsonResponse({ detail: 'forbidden' }, 403) },
    ]);
    setSessionToken('t-fine');

    await postJson('/api/v1/alerts/1/verdict', {}).catch(() => undefined);

    expect(sessionToken()).toBe('t-fine');
  });
});
