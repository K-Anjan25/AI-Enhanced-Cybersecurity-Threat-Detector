/**
 * The alert batch's export, end to end over a stubbed network (T-415).
 *
 * `fetch` is the only thing faked, so an assertion here is an assertion about the
 * request the screen made or about what it said afterwards — the two things the
 * acceptance criterion turns into evidence:
 *
 *   * **the exported rows are the filtered view's rows** — asserted from the body
 *     that left the browser: the window is the queue's own 24 hours (so the file
 *     cannot cover a different range than the panel), the order and page size are
 *     the queue's, and the format is in the body because the same route serves both.
 *   * **the screen says what happened** — how many rows left, whether the window held
 *     more, and that the trail records it (an egress is a thing that is written down).
 *
 * Downloads cannot happen in jsdom (`URL.createObjectURL` is not implemented), so the
 * object URL and the anchor's click are defined here and removed afterwards, exactly
 * as the hunt console's export tests do it.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { renderWithProviders, stubFetch, textResponse, type StubRoute } from '../../../test/query';
import { QUEUE_LIMIT, QUEUE_WINDOW_MS } from '../api';
import { ExportControls } from './ExportControls';

const CSV = 'id,created_at\r\n1,2026-10-06T10:00:00+00:00\r\n';
const FILENAME = 'aegis-alerts-2026-10-05T10-00-00+00-00-to-2026-10-06T10-00-00+00-00.csv';

/** The two browser APIs jsdom does not implement, plus the click that navigates. */
function stubDownload() {
  const created: Blob[] = [];
  const click = vi.fn();
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: (blob: Blob) => {
      created.push(blob);
      return 'blob:stub';
    },
  });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(click);
  return { created, click };
}

/** The file the anchor was pointed at, read through the object URL stub. */
function saved(created: Blob[]): { blob: Blob | undefined } {
  return { blob: created[0] };
}

function route(respond: StubRoute['respond']): StubRoute[] {
  return [{ match: '/api/v1/alerts/export', respond }];
}

function csvAnswer(headers: Record<string, string> = {}): Response {
  const response = textResponse(CSV);
  for (const [name, value] of Object.entries({
    // The real response's media type, which `postExport` keeps on the blob.
    'content-type': 'text/csv',
    'content-disposition': `attachment; filename="${FILENAME}"`,
    'x-export-rows': '1',
    'x-export-truncated': 'false',
    ...headers,
  })) {
    response.headers.set(name, value);
  }
  return response;
}

// Defined for every test, not only the ones that assert on it: a test that lets a
// download succeed without these stubs leaves `saveFile` throwing inside the
// mutation's `onSuccess`, which vitest then reports as an unhandled error rather
// than as a failure of the test that caused it.
let download: ReturnType<typeof stubDownload>;

beforeEach(() => {
  download = stubDownload();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(URL, 'createObjectURL');
  Reflect.deleteProperty(URL, 'revokeObjectURL');
});

describe('the alert batch export', () => {
  it('exports the queue\u2019s own window, filters and page size', async () => {
    const user = userEvent.setup();
    const seen = stubFetch(route(() => csvAnswer()));
    renderWithProviders(<ExportControls />);

    await user.click(screen.getByRole('button', { name: 'Export CSV' }));

    await waitFor(() => {
      expect(seen).toHaveLength(1);
    });
    const request = seen[0]!;
    expect(new URL(request.url).pathname).toBe('/api/v1/alerts/export');
    expect(request.method).toBe('POST');
    const body = (await request.json()) as Record<string, unknown>;
    expect(body['format']).toBe('csv');
    expect(body['limit']).toBe(QUEUE_LIMIT);
    expect(body['order']).toBe('desc');
    // The window is the queue's 24 hours, taken at the click: the file cannot cover
    // a different range than the panel standing next to it.
    const start = Date.parse(String(body['start']));
    const end = Date.parse(String(body['end']));
    expect(end - start).toBe(QUEUE_WINDOW_MS);
    // A cursor is not in the body at all, because the API refuses one.
    expect('cursor' in body).toBe(false);
  });

  it('saves the file the server named, and reports how many rows left', async () => {
    const user = userEvent.setup();
    const { created, click } = download;
    stubFetch(route(() => csvAnswer()));
    renderWithProviders(<ExportControls />);

    await user.click(screen.getByRole('button', { name: 'Export CSV' }));

    const message = await screen.findByText(/Exported 1 row as CSV/);
    expect(message).toHaveTextContent('The export is recorded in the audit trail');
    expect(click).toHaveBeenCalledTimes(1);
    expect(saved(created).blob?.type).toContain('text/csv');
    // The name is the server's, because it carries the window (T-408's rule); the
    // anchor's `download` is what a browser reads.
    expect(document.querySelector('a')).toBeNull();
  });

  it('takes the row count from the server rather than counting the file', async () => {
    // One data row in the CSV, nine reported: the number in the sentence has to be
    // the server's, because a PDF cannot be counted here at all and two counts that
    // can disagree are worse than one that is stated.
    const user = userEvent.setup();
    stubFetch(route(() => csvAnswer({ 'x-export-rows': '9' })));
    renderWithProviders(<ExportControls />);

    await user.click(screen.getByRole('button', { name: 'Export CSV' }));

    expect(await screen.findByText(/Exported 9 rows as CSV/)).toBeInTheDocument();
  });

  it('asks for a PDF when the report is the one wanted', async () => {
    const user = userEvent.setup();
    const seen = stubFetch(
      route(() => {
        const response = new Response(new Blob(['%PDF-1.4'], { type: 'application/pdf' }), {
          headers: {
            'content-type': 'application/pdf',
            'content-disposition': 'attachment; filename="aegis-alerts.pdf"',
            'x-export-rows': '2',
          },
        });
        return response;
      }),
    );
    renderWithProviders(<ExportControls />);

    await user.click(screen.getByRole('button', { name: 'Export PDF' }));

    expect(await screen.findByText(/Exported 2 rows as PDF/)).toBeInTheDocument();
    const request = seen[0]!;
    expect(request.headers.get('accept')).toBe('application/pdf');
    const body = (await request.json()) as Record<string, unknown>;
    expect(body['format']).toBe('pdf');
  });

  it('says when the window held more than the file does', async () => {
    const user = userEvent.setup();
    stubFetch(route(() => csvAnswer({ 'x-export-truncated': 'true' })));
    renderWithProviders(<ExportControls />);

    await user.click(screen.getByRole('button', { name: 'Export CSV' }));

    expect(await screen.findByText(/window holds more rows than the file/)).toBeInTheDocument();
  });

  it('reports a refusal as the server\u2019s own, and downloads nothing', async () => {
    const user = userEvent.setup();
    const { created, click } = download;
    stubFetch(route(() => new Response(JSON.stringify({ detail: 'no' }), { status: 403 })));
    renderWithProviders(<ExportControls />);

    await user.click(screen.getByRole('button', { name: 'Export CSV' }));

    expect(await screen.findByText(/needs the responder role/)).toBeInTheDocument();
    expect(screen.getByText(/nothing was written to the audit trail/)).toBeInTheDocument();
    expect(click).not.toHaveBeenCalled();
    expect(created).toHaveLength(0);
  });

  it('disables both controls while an export is in flight', async () => {
    const user = userEvent.setup();
    let release: (() => void) | undefined;
    const held = new Promise<Response>((resolve) => {
      release = () => {
        resolve(csvAnswer());
      };
    });
    stubFetch(route(() => held));
    renderWithProviders(<ExportControls />);

    await user.click(screen.getByRole('button', { name: 'Export CSV' }));

    expect(screen.getByRole('button', { name: 'Exporting…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeDisabled();

    release?.();
    await screen.findByText(/Exported 1 row as CSV/);
  });

  it('has no serious accessibility violations', async () => {
    const { container } = renderWithProviders(<ExportControls />);

    await expectAccessible(container);
  });
});
