/**
 * Test helpers for the overview's data layer.
 *
 * `fetch` is the boundary these tests stub: everything above it is real code —
 * React Query, the page, every aggregation — and everything below it is the
 * network. That is deliberately the only thing faked, so a test asserting on the
 * rendered output is asserting on what the app produced from a given answer.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import { type ReactElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { ThemeProvider } from '../theme/ThemeProvider';

/** A response builder, so a stub reads like the endpoint it stands for. */
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

export function textResponse(body: string, status = 200): Response {
  return new Response(body, { status, headers: { 'content-type': 'text/plain' } });
}

export interface StubRoute {
  /** A path prefix the route answers. */
  match: string;
  /** The answer, or a function of the request. */
  respond: (request: Request) => Response | Promise<Response>;
}

/**
 * Install a routing `fetch` stub and return the requests it saw.
 *
 * An unmatched path is a 404 rather than a thrown error: a test that forgot a
 * route should see the app's error state, not an unrelated TypeError.
 */
export function stubFetch(routes: readonly StubRoute[]): Request[] {
  const seen: Request[] = [];
  vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(
      typeof input === 'string' ? new URL(input, window.location.origin).toString() : input,
      init,
    );
    seen.push(request);
    const url = new URL(request.url);
    const route = routes.find((candidate) => url.pathname.startsWith(candidate.match));
    if (route === undefined) return Promise.resolve(jsonResponse({ detail: 'no route' }, 404));
    return Promise.resolve(route.respond(request));
  });
  return seen;
}

/** A query client with retries off, so a failure is a failure on the first try. */
export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, refetchOnWindowFocus: false, staleTime: 0 },
    },
  });
}

export function Providers({ children, client }: { children: ReactNode; client?: QueryClient }) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={client ?? testQueryClient()}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

/** Render inside the providers every screen expects. */
export function renderWithProviders(ui: ReactElement, client?: QueryClient): RenderResult {
  return render(<Providers {...(client === undefined ? {} : { client })}>{ui}</Providers>);
}
