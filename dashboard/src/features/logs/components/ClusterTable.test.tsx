/**
 * The cluster row, asserted on what design.md §4.5 says a row must carry.
 *
 * The rail is the half of that rule jsdom can see: §4.5 marks a row holding an error
 * or worse with a left border *and* the severity colour, because colour alone fails
 * NFR-09. The chip's text is asserted too — a level label names the level the sender
 * declared, not a severity anyone scored, so it must stay the level's own word.
 */
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Providers } from '../../../test/query';
import { buildLogView } from '../view';
import { tailWindow } from '../cluster';
import { ClusterTable } from './ClusterTable';
import type { LogCluster, LogTail } from '../api';

const WINDOW = tailWindow(Date.parse('2026-10-06T10:05:00Z'), 300_000);

function cluster(overrides: Partial<LogCluster>): LogCluster {
  return {
    key: 't-1',
    template_id: 't-1',
    count: 1,
    first_seen: '2026-10-06T10:00:00Z',
    last_seen: '2026-10-06T10:00:09Z',
    worst_level: 'info',
    levels: { info: 1 },
    hosts: ['web-1'],
    services: ['api'],
    sample_message: 'connection refused',
    parameters: {},
    ...overrides,
  };
}

const TAIL: LogTail = {
  start: '2026-10-06T10:00:00Z',
  end: '2026-10-06T10:05:00Z',
  clusters: [
    cluster({
      key: 't-error',
      template_id: 't-error',
      count: 4,
      worst_level: 'error',
      levels: { error: 4 },
    }),
    cluster({
      key: 't-quiet',
      template_id: 't-quiet',
      count: 2,
      worst_level: 'info',
      levels: { info: 2 },
    }),
  ],
  lines_seen: 6,
  clusters_seen: 2,
  clusters_truncated: false,
  retained_from: '2026-10-06T10:00:00Z',
  retained_to: '2026-10-06T10:00:09Z',
  retained_lines: 6,
  dropped_lines: 0,
  caveats: ['not a store', 'Nothing matched these filters'],
};

function renderTable() {
  const view = buildLogView({ tail: TAIL, window: WINDOW, failed: false });
  render(
    <Providers>
      <ClusterTable rows={view.rows} openKey={null} onOpen={() => undefined} empty={<p>empty</p>} />
    </Providers>,
  );
  return within(screen.getByRole('table', { name: /Log clusters/ }));
}

/** The cells of one body row, in column order — resolved from the header, never assumed. */
function cellsOf(table: ReturnType<typeof within>, index: number): HTMLElement[] {
  const rows = table.getAllByRole('row').slice(1);
  return within(rows[index] as HTMLElement).getAllByRole('cell') as HTMLElement[];
}

function levelCell(table: ReturnType<typeof within>, index: number): HTMLElement {
  const header = table.getAllByRole('row')[0] as HTMLElement;
  const column = within(header)
    .getAllByRole('columnheader')
    .findIndex((cell) => cell.textContent === 'Level');
  const cell = cellsOf(table, index)[column];
  if (cell === undefined) throw new Error('no level cell');
  return cell;
}

describe('ClusterTable', () => {
  it('says a row holds an error or worse, not only with a colour', () => {
    const table = renderTable();

    expect(within(levelCell(table, 0)).getByText(/\(error or worse\)/)).toBeInTheDocument();
    expect(within(levelCell(table, 1)).queryByText(/\(error or worse\)/)).toBeNull();
  });

  it('labels the chip with the level’s own word', () => {
    const table = renderTable();

    // "error" is what the line said. Calling it an anomaly here would be the claim
    // §4.5 makes and this build cannot support (T-419).
    expect(within(levelCell(table, 0)).getByText('error')).toBeInTheDocument();
    expect(within(levelCell(table, 1)).getByText('info')).toBeInTheDocument();
  });

  it('is a real table, addressed by its rows’ keys', () => {
    const table = renderTable();

    expect(table.getByRole('button', { name: 't-error' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(table.getByText('×4')).toBeInTheDocument();
  });
});
