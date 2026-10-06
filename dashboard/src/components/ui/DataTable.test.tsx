import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { type Column, DataTable } from './DataTable';

interface Alert {
  id: string;
  title: string;
  score: number;
  source: string;
}

const COLUMNS: Column<Alert>[] = [
  { id: 'title', header: 'Alert', cell: (row) => row.title, sortValue: (row) => row.title },
  {
    id: 'score',
    header: 'Score',
    cell: (row) => row.score.toFixed(2),
    sortValue: (row) => row.score,
  },
  { id: 'source', header: 'Source', cell: (row) => row.source },
  { id: 'id', header: 'ID', cell: (row) => row.id, hiddenByDefault: true },
];

const ROWS: Alert[] = [
  { id: 'a2', title: 'Beaconing to unknown host', score: 0.91, source: 'zeek' },
  { id: 'a1', title: 'Login failure burst', score: 0.42, source: 'auth' },
  { id: 'a3', title: 'Port scan from internal host', score: 0.77, source: 'zeek' },
];

function renderTable(props: Partial<React.ComponentProps<typeof DataTable<Alert>>> = {}) {
  return render(
    <DataTable
      caption="Alerts"
      columns={COLUMNS}
      rows={ROWS}
      rowKey={(row) => row.id}
      rowLabel={(row) => row.title}
      {...props}
    />,
  );
}

/** The body rows, in render order. */
function bodyRows(): HTMLElement[] {
  return within(screen.getByRole('table')).getAllByRole('row').slice(1);
}

/** The first cell of each body row that is not the selection cell. */
function firstTitles(): string[] {
  return bodyRows().map((row) => within(row).getAllByRole('cell')[1]?.textContent ?? '');
}

describe('DataTable', () => {
  it('renders the headers and one row per record', () => {
    renderTable();

    expect(screen.getByRole('table', { name: 'Alerts' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Alert' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Score' })).toBeInTheDocument();
    expect(bodyRows()).toHaveLength(3);
    expect(screen.getByText('Login failure burst')).toBeInTheDocument();
  });

  it('sorts by a column when its header is pressed, and announces the order', () => {
    renderTable();
    const header = screen.getByRole('columnheader', { name: 'Score' });

    expect(header).toHaveAttribute('aria-sort', 'none');

    fireEvent.click(within(header).getByRole('button', { name: 'Score' }));
    expect(header).toHaveAttribute('aria-sort', 'ascending');
    expect(firstTitles()).toEqual([
      'Login failure burst',
      'Port scan from internal host',
      'Beaconing to unknown host',
    ]);

    fireEvent.click(within(header).getByRole('button', { name: 'Score' }));
    expect(header).toHaveAttribute('aria-sort', 'descending');
    expect(firstTitles()[0]).toBe('Beaconing to unknown host');
  });

  it('offers no sort on a column that has no sort value', () => {
    renderTable();

    const header = screen.getByRole('columnheader', { name: 'Source' });
    expect(header).not.toHaveAttribute('aria-sort');
    expect(within(header).queryByRole('button')).not.toBeInTheDocument();
  });

  it('hides a column by default and lets the picker switch it back on', () => {
    renderTable();
    expect(screen.queryByRole('columnheader', { name: 'ID' })).not.toBeInTheDocument();

    const picker = screen.getByRole('checkbox', { name: 'ID' });
    expect(picker).not.toBeChecked();

    fireEvent.click(picker);
    expect(screen.getByRole('columnheader', { name: 'ID' })).toBeInTheDocument();

    fireEvent.click(picker);
    expect(screen.queryByRole('columnheader', { name: 'ID' })).not.toBeInTheDocument();
  });

  it('reports a row selection by key and marks the row selected', () => {
    const onSelectionChange = vi.fn();
    renderTable({ onSelectionChange });

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Login failure burst' }));

    expect(onSelectionChange).toHaveBeenLastCalledWith(['a1']);
    expect(bodyRows()[1]).toHaveAttribute('aria-selected', 'true');
  });

  it('selects every row, then reports a partial selection honestly', () => {
    const onSelectionChange = vi.fn();
    renderTable({ onSelectionChange });
    const all = screen.getByRole('checkbox', { name: 'Select all rows' }) as HTMLInputElement;

    fireEvent.click(all);
    expect(onSelectionChange).toHaveBeenLastCalledWith(['a2', 'a1', 'a3']);
    expect(all.checked).toBe(true);
    expect(all.indeterminate).toBe(false);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select Login failure burst' }));
    expect(all.checked).toBe(false);
    expect(all.indeterminate).toBe(true);

    fireEvent.click(all);
    expect(all.checked).toBe(true);

    // And a second press clears: the control is a toggle, not a one-way switch.
    fireEvent.click(all);
    expect(onSelectionChange).toHaveBeenLastCalledWith([]);
    expect(all.checked).toBe(false);
    expect(all.indeterminate).toBe(false);
  });

  it('renders only the window of rows inside the viewport', () => {
    const rows: Alert[] = Array.from({ length: 200 }, (_unused, index) => ({
      id: `a${index}`,
      title: `Alert ${index}`,
      score: 0.5,
      source: 'zeek',
    }));
    renderTable({ rows, height: 320 });

    // 320 px of compact rows (200 > 50, so §5.5's compact default) plus the
    // overscan: tens, not two hundred.
    expect(bodyRows().length).toBeLessThan(30);
    expect(screen.getByLabelText('Select Alert 0')).toBeInTheDocument();
    expect(screen.queryByText('Alert 199')).not.toBeInTheDocument();
  });

  it('brings the rows under the scroll position into the DOM', () => {
    const rows: Alert[] = Array.from({ length: 200 }, (_unused, index) => ({
      id: `a${index}`,
      title: `Alert ${index}`,
      score: 0.5,
      source: 'zeek',
    }));
    renderTable({ rows, height: 320 });
    const viewport = screen.getAllByRole('rowgroup')[1] as HTMLElement;

    // jsdom has no layout, so the scroll position is set on the element directly
    // and then announced — the handler reads it from the event's target.
    Object.defineProperty(viewport, 'scrollTop', { value: 960, configurable: true });
    fireEvent.scroll(viewport);

    expect(screen.getByLabelText('Select Alert 25')).toBeInTheDocument();
    expect(screen.queryByLabelText('Select Alert 0')).not.toBeInTheDocument();
  });

  it('says what is empty, under the real headers', () => {
    renderTable({ rows: [] });

    expect(screen.getByRole('status')).toHaveTextContent('No rows match this view');
    expect(screen.getByRole('columnheader', { name: 'Alert' })).toBeInTheDocument();
  });

  it('lets a caller replace the empty state', () => {
    renderTable({ rows: [], empty: <p>No open critical alerts in the last 24 h.</p> });

    expect(screen.getByText('No open critical alerts in the last 24 h.')).toBeInTheDocument();
  });

  it('has no serious accessibility violations', async () => {
    const { container } = renderTable();

    await expectAccessible(container as HTMLElement);
  });
});
