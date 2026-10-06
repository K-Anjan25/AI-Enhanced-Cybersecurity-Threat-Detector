/**
 * The audit panel (T-410, design.md §4.8: append-only, filterable, exportable, visibly
 * non-editable).
 *
 * Three claims are tested as the operator meets them: an entry renders with its actor,
 * action, target, context and source; the filters go out as query parameters, since a
 * filter the route did not receive is a filter that filters nothing; and the CSV the
 * button produces is built from the rows on screen. The last of those is asserted on the
 * Blob the download was made from — the same technique the hunt console's export test
 * uses (T-408) — because "exportable" means a file, not a promise.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { jsonResponse, renderWithProviders, stubFetch } from '../../../test/query';
import { AuditPanel } from './AuditPanel';

const AUDIT = '/api/v1/audit';

const ENTRIES = {
  items: [
    {
      id: 91,
      actor: 'ops@example.test',
      action: 'threshold.set',
      target_type: 'threshold',
      target_id: 'flow/high',
      detail: { previous: 0.7, applied: 0.8 },
      ip: '10.0.0.7',
      at: '2026-10-06T10:00:00Z',
    },
    {
      id: 90,
      actor: 'analyst@example.test',
      action: 'alert.verdict',
      target_type: 'alert',
      target_id: '42',
      detail: { verdict: 'true_positive' },
      ip: null,
      at: '2026-10-06T09:00:00Z',
    },
  ],
  next_before: 90,
};

/**
 * A download, in jsdom.
 *
 * `URL.createObjectURL` is not implemented there, so it is defined rather than spied
 * on, and the anchor's `click` is stubbed so the test does not navigate the document
 * to a blob URL it cannot resolve — the same shape the hunt console's export test
 * uses (T-408).
 */
function stubDownload(): { blobs: Blob[]; restore: () => void } {
  const blobs: Blob[] = [];
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    writable: true,
    value: (blob: Blob) => {
      blobs.push(blob);
      return 'blob:aegis-test';
    },
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    writable: true,
    value: () => undefined,
  });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  return {
    blobs,
    restore: () => {
      Reflect.deleteProperty(URL, 'createObjectURL');
      Reflect.deleteProperty(URL, 'revokeObjectURL');
      click.mockRestore();
    },
  };
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AuditPanel', () => {
  it('renders an entry with its actor, action, target and context', async () => {
    stubFetch([{ match: AUDIT, respond: () => jsonResponse(ENTRIES) }]);
    const { container } = renderWithProviders(<AuditPanel />);

    expect(await screen.findByText('threshold.set')).toBeInTheDocument();
    expect(screen.getByText('ops@example.test')).toBeInTheDocument();
    expect(screen.getByText('threshold:flow/high')).toBeInTheDocument();
    expect(screen.getByText('applied=0.8 previous=0.7')).toBeInTheDocument();
    await expectAccessible(container);
  });

  it('says the window is bounded and the trail is append-only', async () => {
    stubFetch([{ match: AUDIT, respond: () => jsonResponse(ENTRIES) }]);
    renderWithProviders(<AuditPanel />);
    const note = await screen.findByTestId('audit-note');
    expect(note).toHaveTextContent('page cap was reached');
    expect(note).toHaveTextContent('no edit or delete anywhere, in any role');
  });

  it('offers the older page only when the route said there is one', async () => {
    const user = userEvent.setup();
    const seen = stubFetch([
      {
        match: AUDIT,
        respond: (request) =>
          new URL(request.url).searchParams.has('before')
            ? jsonResponse({ items: [], next_before: null })
            : jsonResponse(ENTRIES),
      },
    ]);
    renderWithProviders(<AuditPanel />);

    await user.click(await screen.findByRole('button', { name: 'Older entries in this window' }));
    await waitFor(() => {
      expect(screen.getByTestId('audit-note')).toHaveTextContent('fully read');
    });
    const paged = seen.filter((request) => new URL(request.url).searchParams.has('before'));
    expect(paged).toHaveLength(1);
    expect(new URL(paged[0]?.url ?? '').searchParams.get('before')).toBe('90');
  });

  it('sends the filters it offers as query parameters', async () => {
    const user = userEvent.setup();
    const seen = stubFetch([{ match: AUDIT, respond: () => jsonResponse(ENTRIES) }]);
    renderWithProviders(<AuditPanel />);

    await screen.findByText('threshold.set');
    // By role, not by label: the column picker also labels a control "Action".
    await user.selectOptions(screen.getByRole('combobox', { name: 'Action' }), 'user.role');
    await user.type(screen.getByRole('textbox', { name: 'Actor' }), 'ops@example.test');
    await user.type(screen.getByRole('textbox', { name: 'Target id' }), 'flow/high');

    // The last request is the one asserted: each keystroke re-queries, so a request
    // from halfway through the typing would satisfy a weaker check and prove nothing.
    await waitFor(() => {
      const last = new URL(seen[seen.length - 1]?.url ?? '');
      expect(last.searchParams.get('action')).toBe('user.role');
      expect(last.searchParams.get('actor')).toBe('ops@example.test');
      expect(last.searchParams.get('target_id')).toBe('flow/high');
      expect(last.searchParams.get('limit')).toBe('50');
      // The window is required by the route, and it is always sent.
      expect(last.searchParams.get('start')).not.toBeNull();
      expect(last.searchParams.get('end')).not.toBeNull();
    });
  });

  it('exports the rows that are on screen, quoted so a comma cannot shift a column', async () => {
    const user = userEvent.setup();
    const download = stubDownload();
    stubFetch([
      {
        match: AUDIT,
        respond: () =>
          jsonResponse({
            items: [{ ...ENTRIES.items[0], actor: 'ops, on call' }, ENTRIES.items[1]],
            next_before: null,
          }),
      },
    ]);
    renderWithProviders(<AuditPanel />);

    await user.click(await screen.findByRole('button', { name: 'Export CSV' }));
    expect(download.blobs).toHaveLength(1);
    const csv = await readBlob(download.blobs[0]);
    const lines = csv.trimEnd().split('\n');
    expect(lines[0]).toBe('id,at,actor,action,target,detail,ip');
    expect(lines).toHaveLength(3);
    expect(lines[1]).toContain('"ops, on call"');
    expect(lines[1]?.endsWith(',10.0.0.7')).toBe(true);
    expect(lines[2]).toContain('alert.verdict');
    // The source address is in the export whether or not its column is shown: the
    // file is the record, and an absent one reads as absent rather than as empty.
    expect(lines[2]?.endsWith(',not recorded')).toBe(true);
    download.restore();
  });

  it('offers no export when there is nothing to export', async () => {
    stubFetch([{ match: AUDIT, respond: () => jsonResponse({ items: [], next_before: null }) }]);
    renderWithProviders(<AuditPanel />);
    expect(await screen.findByTestId('audit-empty')).toHaveTextContent(
      'No recorded action falls in this window',
    );
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeDisabled();
  });

  it('reads a failed trail as a failure, not as an empty window', async () => {
    stubFetch([{ match: AUDIT, respond: () => jsonResponse({ detail: 'no' }, 500) }]);
    renderWithProviders(<AuditPanel />);
    expect(await screen.findByText('The audit trail could not be read')).toBeInTheDocument();
    expect(screen.queryByTestId('audit-empty')).toBeNull();
  });
});
