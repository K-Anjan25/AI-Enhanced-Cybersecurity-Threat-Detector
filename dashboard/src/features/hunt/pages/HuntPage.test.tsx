/**
 * The hunt console, end to end through the page an analyst opens.
 *
 * The only faked things are the network (`fetch`, via the shared stub) and the URL
 * object used for the download. Everything between — the parser, the query, the view
 * model, the components — is the real code, so an assertion here is an assertion
 * about what the screen says.
 *
 * The two acceptance criteria of T-408 are asserted where they are visible: the
 * export is refused for a role the server does not permit and *says* the refusal
 * wrote no audit entry, and an empty result renders the executed query and the time
 * range. The state that is easiest to get wrong — "nothing searched yet" being
 * presented as "nothing found" — has its own test.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AlertRow } from '../../../api/alerts';
import { ToastProvider } from '../../../components/ui';
import { expectAccessible } from '../../../test/axe';
import { jsonResponse, Providers, stubFetch, textResponse } from '../../../test/query';
import { HuntPage } from './HuntPage';

const START = Date.parse('2026-10-06T09:00:00Z');

function row(overrides: Partial<AlertRow> & { id: number }): AlertRow {
  return {
    created_at: new Date(START + 60_000).toISOString(),
    entity_id: 7,
    family: 'exfiltration',
    severity: 'high',
    score: 0.8123,
    status: 'open',
    first_seen: new Date(START).toISOString(),
    last_seen: new Date(START + 3_000_000).toISOString(),
    occurrence_count: 1_234,
    trace_id: 'trace-abc',
    ...overrides,
  };
}

function page(items: AlertRow[], next: string | null = null) {
  return { items, next_cursor: next, limit: 100, order: 'desc' };
}

/** The paths the stub saw, newest last. */
function stubHunt(
  alerts: (request: Request) => Response | Promise<Response>,
  exportAnswer: () => Response = () => textResponse('id,created_at\r\n1,2026-10-06T09:01:00Z\r\n'),
) {
  return stubFetch([
    { match: '/api/v1/hunt/export', respond: exportAnswer },
    { match: '/api/v1/alerts', respond: alerts },
  ]);
}

/**
 * A download, in jsdom.
 *
 * `URL.createObjectURL` is not implemented there (the same gap that leaves jsdom
 * without a `PointerEvent`), so it is defined rather than spied on, and removed
 * again in `afterEach`. Stubbing the anchor's `click` is what keeps the test from
 * navigating the jsdom document to a blob URL it cannot resolve.
 */
function stubDownload() {
  const created: Blob[] = [];
  const click = vi.fn();
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    writable: true,
    value: (blob: Blob) => {
      created.push(blob);
      return 'blob:aegis';
    },
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    writable: true,
    value: () => undefined,
  });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(click);
  return { created, click };
}

/** Read a blob back, through the one API jsdom does implement for it. */
function readBlob(blob: Blob | undefined): Promise<string> {
  return new Promise((resolve, reject) => {
    if (blob === undefined) {
      reject(new Error('nothing was downloaded'));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      resolve(String(reader.result));
    };
    reader.onerror = () => {
      reject(reader.error ?? new Error('the blob could not be read'));
    };
    reader.readAsText(blob);
  });
}

/**
 * The page as the app mounts it: the toast provider comes from `App.tsx`, so a test
 * that mounts the page alone has to supply it. It is wrapped here rather than added
 * to the shared test providers because `src/test` sits below `src/components` in the
 * layering the boundary check enforces.
 */
function renderHunt(entries: string[] = ['/hunt']) {
  return render(
    <Providers initialEntries={entries}>
      <ToastProvider>
        <HuntPage />
      </ToastProvider>
    </Providers>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(URL, 'createObjectURL');
  Reflect.deleteProperty(URL, 'revokeObjectURL');
  window.localStorage.clear();
});

describe('the hunt console', () => {
  it('does not search until asked, and says so rather than showing an empty table', async () => {
    const seen = stubHunt(() => jsonResponse(page([])));
    renderHunt();

    expect(screen.getByRole('heading', { level: 1, name: 'Hunt' })).toBeInTheDocument();
    expect(screen.getByText(/Nothing has been searched yet/)).toBeInTheDocument();
    expect(seen).toEqual([]);
  });

  it('runs the query, shows the rows and echoes what was searched', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubHunt(() =>
      jsonResponse(page([row({ id: 1 }), row({ id: 2, severity: 'low', family: 'c2' })])),
    );
    renderHunt();

    await user.type(screen.getByRole('combobox', { name: 'Query' }), 'severity:high');
    await user.click(screen.getByRole('button', { name: 'Run hunt' }));

    expect(await screen.findByRole('cell', { name: 'exfiltration' })).toBeInTheDocument();
    expect(screen.getByTestId('hunt-echo')).toHaveTextContent(
      'Searched severity:high order:desc limit:100',
    );
    expect(screen.getByText(/2 rows in/)).toBeInTheDocument();
  });

  it('renders the executed query and the time range when nothing matched (§4.6)', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubHunt(() => jsonResponse(page([])));
    renderHunt();

    await user.type(screen.getByRole('combobox', { name: 'Query' }), 'family:lateral-movement');
    await user.click(screen.getByRole('button', { name: 'Run hunt' }));

    const empty = await screen.findByText('No alert matched');
    expect(empty).toBeInTheDocument();
    // The title and the description both reach the analyst: the first says what
    // happened, the second says what was searched to get there.
    // The reason names both the query and the window, which is the whole point of
    // rendering it: an empty table alone cannot be told from a typo.
    const reason = screen.getByText(/family:lateral-movement order:desc limit:100 between/);
    expect(reason).toBeInTheDocument();
    expect(screen.getByTestId('hunt-echo')).toHaveTextContent('order:desc limit:100');
  });

  it('refuses a term it cannot read before searching anything', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const seen = stubHunt(() => jsonResponse(page([])));
    renderHunt();

    await user.type(screen.getByRole('combobox', { name: 'Query' }), 'src_ip:10.0.0.7');

    expect(screen.getByText(/not a field this build can search/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run hunt' })).toBeDisabled();
    expect(seen).toEqual([]);
  });

  it('offers a field it cannot search as a refusal, with the reason', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubHunt(() => jsonResponse(page([])));
    renderHunt();

    await user.type(screen.getByRole('combobox', { name: 'Query' }), 'src');

    const options = screen.getAllByRole('option');
    expect(options.map((option) => option.textContent)).toContain(
      'src_ip:not searchable — raw flow records have no read API in this build (T-418)',
    );
  });

  it('re-runs the hunt when the window changes, so the table cannot disagree with the selector', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const seen = stubHunt(() => jsonResponse(page([])));
    renderHunt();

    await user.click(screen.getByRole('button', { name: 'Run hunt' }));
    await screen.findByText('No alert matched');
    await user.selectOptions(screen.getByLabelText('Window'), '7d');

    await waitFor(() => {
      const spans = seen.map(
        (request) =>
          (Date.parse(new URL(request.url).searchParams.get('end') ?? '') -
            Date.parse(new URL(request.url).searchParams.get('start') ?? '')) /
          86_400_000,
      );
      expect(spans).toEqual([1, 7]);
    });
  });

  it('exports the query that is on screen, and reports the rows and the audit entry', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const seen = stubHunt(() => jsonResponse(page([row({ id: 1 })])));
    const download = stubDownload();
    renderHunt();

    await user.type(screen.getByRole('combobox', { name: 'Query' }), 'severity:high');
    await user.click(screen.getByRole('button', { name: 'Run hunt' }));
    await screen.findByRole('cell', { name: 'exfiltration' });
    await user.click(screen.getByRole('button', { name: 'Export CSV' }));

    await waitFor(() => {
      expect(screen.getByText(/Exported 1 rows as CSV/)).toBeInTheDocument();
    });
    expect(screen.getByText(/recorded in the audit trail/)).toBeInTheDocument();
    expect(download.click).toHaveBeenCalled();

    const exported = seen.find(
      (request) => new URL(request.url).pathname === '/api/v1/hunt/export',
    );
    const body = (await exported?.clone().json()) as Record<string, unknown>;
    expect(body['severity']).toBe('high');
    expect(body['order']).toBe('desc');
    expect(body['limit']).toBe(100);

    // The download is the document the server rendered, read back out of the blob.
    const blob = download.created[0];
    expect(blob?.type).toContain('text/csv');
    expect(await readBlob(blob)).toContain('id,created_at');
  });

  it('cannot export before a hunt has run, because there is no query to export', async () => {
    stubHunt(() => jsonResponse(page([])));
    renderHunt();

    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeDisabled();
  });

  it('says the export was refused, and that nothing was written, when the role is not permitted', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubHunt(
      () => jsonResponse(page([])),
      () => jsonResponse({ detail: "role 'analyst' is not permitted on this route" }, 403),
    );
    renderHunt();

    await user.click(screen.getByRole('button', { name: 'Run hunt' }));
    await screen.findByText('No alert matched');
    await user.click(screen.getByRole('button', { name: 'Export CSV' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Exporting needs the responder role');
    expect(alert).toHaveTextContent('nothing was written to the audit trail');
  });

  it('says that saved hunts live in this browser, and that creating an alert is unavailable', () => {
    stubHunt(() => jsonResponse(page([])));
    renderHunt();

    expect(
      screen.getByText(/Creating an alert from a filter is not available/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Saved hunts \(0\)/ })).toBeInTheDocument();
  });

  it('saves a hunt, reloads it into the box, runs it, and can forget it', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubHunt(() => jsonResponse(page([])));
    renderHunt();

    const box = screen.getByRole('combobox', { name: 'Query' });
    await user.type(box, 'status:open');
    await user.type(screen.getByLabelText('Save as'), 'open queue');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(screen.getByRole('button', { name: 'Saved hunts (1)' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Saved hunts (1)' }));

    // The menu states the store's boundary rather than implying a shared one.
    expect(screen.getByText(/live in this browser only/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'open queue' }));
    expect(box).toHaveValue('status:open');

    await user.click(screen.getByRole('button', { name: 'Saved hunts (1)' }));
    await user.click(screen.getByRole('button', { name: 'Forget' }));
    expect(screen.getByRole('button', { name: 'Saved hunts (0)' })).toBeInTheDocument();
  });

  it('remembers a hunt that ran in the recent list, so it can be re-run without retyping', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubHunt(() => jsonResponse(page([])));
    renderHunt();

    await user.type(screen.getByRole('combobox', { name: 'Query' }), 'severity:high');
    await user.click(screen.getByRole('button', { name: 'Run hunt' }));
    await screen.findByText('No alert matched');

    await user.click(screen.getByRole('button', { name: /Saved hunts/ }));
    expect(
      screen.getByRole('button', { name: 'severity:high order:desc limit:100' }),
    ).toBeInTheDocument();
  });

  it('reports a read the API refused rather than showing an empty window as a fact', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubHunt(() => jsonResponse({ detail: 'window is too wide' }, 400));
    renderHunt();

    await user.click(screen.getByRole('button', { name: 'Run hunt' }));

    expect(await screen.findByText('The hunt could not be read')).toBeInTheDocument();
    expect(screen.getByText(/The API refused the query/)).toBeInTheDocument();
  });

  it('runs a hunt named in the URL, which is how the palette opens a saved one (T-411)', async () => {
    // A saved hunt is a query, not a window: the console reads the text from the URL
    // and applies its own default window, exactly as if it had been typed.
    const seen = stubHunt(() => jsonResponse(page([row({ id: 1 })])));
    renderHunt(['/hunt?q=severity%3Ahigh']);

    expect(await screen.findByRole('cell', { name: 'exfiltration' })).toBeInTheDocument();
    expect(screen.getByTestId('hunt-echo')).toHaveTextContent('Searched severity:high');
    expect(seen).toHaveLength(1);
  });

  it('puts an unreadable URL query in the box and asks for nothing', async () => {
    // The refusal is the input's own: firing a request the API must reject would
    // report a server error for what is a typo.
    const seen = stubHunt(() => jsonResponse(page([])));
    renderHunt(['/hunt?q=src_ip%3A10.0.0.1']);

    expect(screen.getByRole('combobox', { name: 'Query' })).toHaveValue('src_ip:10.0.0.1');
    expect(screen.getByText(/is not a field this build can search/i)).toBeInTheDocument();
    expect(seen).toEqual([]);
  });

  it('searches once for a URL query, even after the box is edited', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const seen = stubHunt(() => jsonResponse(page([row({ id: 1 })])));
    renderHunt(['/hunt?q=severity%3Ahigh']);
    await screen.findByRole('cell', { name: 'exfiltration' });

    await user.type(screen.getByRole('combobox', { name: 'Query' }), 'x');

    // Editing the box must not re-run the hunt from the URL: the table answers the
    // question that was asked, not the one being typed.
    expect(seen).toHaveLength(1);
  });

  it('has no critical accessibility violations in the idle and empty states', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubHunt(() => jsonResponse(page([])));
    const { container } = renderHunt();

    await expectAccessible(container);

    await user.click(screen.getByRole('button', { name: 'Run hunt' }));
    await screen.findByText('No alert matched');
    await expectAccessible(container);
  });
});

describe('the results table', () => {
  it('links an alert to the triage screen with both halves of its key', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubHunt(() => jsonResponse(page([row({ id: 42 })])));
    renderHunt();

    await user.click(screen.getByRole('button', { name: 'Run hunt' }));

    const link = await screen.findByRole('link', { name: /06 Oct 2026/ });
    expect(link).toHaveAttribute(
      'href',
      expect.stringContaining('/alerts/42?created_at=2026-10-06T09%3A01%3A00.000Z'),
    );
  });

  it('hides the low-value columns by default and offers them back', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubHunt(() => jsonResponse(page([row({ id: 1 })])));
    renderHunt();

    await user.click(screen.getByRole('button', { name: 'Run hunt' }));
    await screen.findByRole('cell', { name: 'exfiltration' });

    const table = screen.getByRole('table', { name: 'Alerts matching this hunt' });
    expect(within(table).queryByRole('columnheader', { name: 'Trace' })).not.toBeInTheDocument();

    // The picker is a `<details>`; jsdom does not apply the disclosure rule, so the
    // checkbox is in the tree without opening it. What is asserted is the table.
    await user.click(screen.getByRole('checkbox', { name: 'Trace' }));
    expect(within(table).getByRole('columnheader', { name: 'Trace' })).toBeInTheDocument();
  });
});
