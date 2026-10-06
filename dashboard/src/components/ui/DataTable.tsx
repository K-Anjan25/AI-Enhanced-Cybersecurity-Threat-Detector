/**
 * DataTable — design.md §6: "virtualised, sortable, column picker, row selection,
 * sticky header, empty state".
 *
 * Every one of those words is a behaviour, so each is implemented as one:
 *
 *   * **virtualised** — only the rows inside the viewport plus `overscan` are in
 *     the DOM, positioned by absolute offset inside a full-height spacer. An alert
 *     list of 20,000 rows renders ~15. The row height comes from
 *     `src/theme/density.ts` and so does the default density ("compact for tables
 *     with more than 50 rows"), because the arithmetic and the CSS must agree.
 *   * **sortable** — a header is a button; the sort is announced with `aria-sort`
 *     on the header cell, which is what tells a screen reader the order changed.
 *   * **column picker** — a `<details>` of checkboxes, native keyboard behaviour and
 *     no popover machinery to get wrong. Hiding a column is a view change, never a
 *     data change.
 *   * **row selection** — controlled or uncontrolled, with a select-all that is
 *     `mixed` when only some rows are picked.
 *   * **sticky header** — outside the scroll container, so it stays put without
 *     scroll synchronisation, and `sticky` for when the page itself scrolls.
 *   * **empty state** — R-29's rule: the empty state says what is empty and sits
 *     inside the table, under the real headers, so the analyst can still see and
 *     sort by what they were looking at.
 *
 * The table is ARIA (`role="table"` and friends) rather than a native `<table>`
 * because a virtualised native table needs `display: block` on its sections, which
 * strips the semantics screen readers rely on. The ARIA roles survive the layout.
 * `aria-rowindex` is absolute, so "row 4,812 of 20,000" is announced even when rows
 * 100–120 are the ones that exist.
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronsUpDown, ChevronUp } from 'lucide-react';

import { defaultDensity, rowHeightPx, type Density } from '../../theme/density';
import { EmptyState } from './EmptyState';

export interface Column<T> {
  /** Stable key, used for sorting state and for the column picker. */
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** The value to sort by. A column without one is not sortable. */
  sortValue?: (row: T) => string | number;
  /** Hidden until switched on in the column picker — the low-value ones. */
  hiddenByDefault?: boolean;
}

export interface DataTableProps<T> {
  /** The table's accessible name. Required: "table" on its own names nothing. */
  caption: string;
  columns: readonly Column<T>[];
  rows: readonly T[];
  rowKey: (row: T) => string;
  /** Accessible name for a row, used to label its own checkbox. */
  rowLabel?: (row: T) => string;
  /** Replaces the built-in empty state. Should still be an `EmptyState`. */
  empty?: ReactNode;
  /** Defaults to the §5.5 rule for the row count. */
  density?: Density;
  /** Viewport height in CSS pixels. Rows outside it are not rendered. */
  height?: number;
  /** Rows rendered beyond the viewport, so a fast scroll does not show a gap. */
  overscan?: number;
  /** Controlled selection. Omit to let the table keep its own. */
  selectedKeys?: readonly string[];
  onSelectionChange?: (keys: string[]) => void;
}

type Direction = 'ascending' | 'descending';

interface Sort {
  columnId: string;
  direction: Direction;
}

/** Selection column width, from the 8-step of §5.5's spacing scale. */
const SELECT_WIDTH = '32px';

/** Default viewport. Not a token: a viewport is a layout choice, not a scale step. */
const DEFAULT_HEIGHT = 480;
const DEFAULT_OVERSCAN = 5;

function compare(a: string | number, b: string | number): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b));
}

export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  rowLabel,
  empty,
  density,
  height = DEFAULT_HEIGHT,
  overscan = DEFAULT_OVERSCAN,
  selectedKeys,
  onSelectionChange,
}: DataTableProps<T>) {
  const [hidden, setHidden] = useState<readonly string[]>(
    columns.filter((column) => column.hiddenByDefault === true).map((column) => column.id),
  );
  const [sort, setSort] = useState<Sort | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [ownSelection, setOwnSelection] = useState<readonly string[]>([]);
  const selectAll = useRef<HTMLInputElement | null>(null);

  const selection = selectedKeys ?? ownSelection;
  const selected = useMemo(() => new Set(selection), [selection]);

  const mode: Density = density ?? defaultDensity(rows.length);
  const rowPx = rowHeightPx(mode);

  const visible = columns.filter((column) => !hidden.includes(column.id));

  const ordered = useMemo(() => {
    if (sort === null) return rows;
    const column = columns.find((candidate) => candidate.id === sort.columnId);
    if (column?.sortValue === undefined) return rows;
    const read = column.sortValue;
    const sorted = [...rows].sort((a, b) => compare(read(a), read(b)));
    return sort.direction === 'ascending' ? sorted : sorted.reverse();
  }, [columns, rows, sort]);

  // The window. `scrollTop` is the container's, and the viewport height is the
  // prop rather than the element's `clientHeight`: the arithmetic must be the same
  // in a test as in a browser, and jsdom has no layout to measure.
  const first = Math.max(0, Math.floor(scrollTop / rowPx) - overscan);
  const last = Math.min(ordered.length, Math.ceil((scrollTop + height) / rowPx) + overscan);
  const windowed = ordered.slice(first, last);

  const allSelected = rows.length > 0 && rows.every((row) => selected.has(rowKey(row)));
  const someSelected = rows.some((row) => selected.has(rowKey(row)));

  // A native checkbox cannot express "some" through JSX, so the ref sets it.
  useEffect(() => {
    if (selectAll.current !== null) selectAll.current.indeterminate = someSelected && !allSelected;
  }, [someSelected, allSelected]);

  function changeSelection(next: readonly string[]) {
    if (selectedKeys === undefined) setOwnSelection(next);
    onSelectionChange?.([...next]);
  }

  function toggleRow(key: string) {
    changeSelection(
      selected.has(key) ? selection.filter((item) => item !== key) : [...selection, key],
    );
  }

  function toggleAll() {
    changeSelection(allSelected ? [] : rows.map((row) => rowKey(row)));
  }

  function toggleSort(column: Column<T>) {
    if (column.sortValue === undefined) return;
    setSort((current) =>
      current?.columnId === column.id && current.direction === 'ascending'
        ? { columnId: column.id, direction: 'descending' }
        : { columnId: column.id, direction: 'ascending' },
    );
  }

  function toggleColumn(id: string) {
    setHidden((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  const template = `${SELECT_WIDTH} repeat(${String(visible.length)}, minmax(0, 1fr))`;
  const columnCount = visible.length + 1;

  return (
    <div>
      <div className="mb-2 flex justify-end">
        <details className="relative">
          <summary className="cursor-pointer rounded-input border border-line bg-surface px-3 py-1 text-body-sm text-ink">
            Columns
          </summary>
          <div
            role="group"
            aria-label="Choose columns"
            className="absolute right-0 z-10 mt-2 flex min-w-full flex-col gap-2 rounded-card border border-line bg-surface p-4 shadow-overlay"
          >
            {columns.map((column) => (
              <label key={column.id} className="flex items-center gap-2 text-body-sm text-ink">
                <input
                  type="checkbox"
                  checked={!hidden.includes(column.id)}
                  onChange={() => toggleColumn(column.id)}
                />
                {column.header}
              </label>
            ))}
          </div>
        </details>
      </div>

      <div
        role="table"
        aria-label={caption}
        aria-rowcount={rows.length + 1}
        aria-colcount={columnCount}
        className="rounded-card border border-line"
      >
        <div
          role="rowgroup"
          className="sticky top-0 z-10 rounded-t-card border-b border-line bg-surface"
        >
          <div role="row" className="grid items-center" style={{ gridTemplateColumns: template }}>
            <div role="columnheader" className="flex h-8 items-center px-3">
              <input
                ref={selectAll}
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                aria-label="Select all rows"
              />
            </div>
            {visible.map((column) => (
              <div
                key={column.id}
                role="columnheader"
                aria-sort={
                  sort?.columnId === column.id
                    ? sort.direction
                    : column.sortValue === undefined
                      ? undefined
                      : 'none'
                }
                className="flex h-8 items-center px-3"
              >
                {column.sortValue === undefined ? (
                  <span className="text-body-sm font-semibold text-muted">{column.header}</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => toggleSort(column)}
                    className="inline-flex items-center gap-2 rounded-input text-body-sm font-semibold text-ink"
                  >
                    {column.header}
                    <span aria-hidden="true">
                      {sort?.columnId !== column.id ? (
                        <ChevronsUpDown className="size-icon-sm" />
                      ) : sort.direction === 'ascending' ? (
                        <ChevronUp className="size-icon-sm" />
                      ) : (
                        <ChevronDown className="size-icon-sm" />
                      )}
                    </span>
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        {rows.length === 0 ? (
          <div role="rowgroup">
            <div role="row">
              <div role="cell" aria-colspan={columnCount} className="p-4">
                {empty ?? <EmptyState title="No rows match this view" />}
              </div>
            </div>
          </div>
        ) : (
          <div
            role="rowgroup"
            onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
            className="relative overflow-y-auto"
            style={{ height: `${String(height)}px` }}
          >
            <div className="relative" style={{ height: `${String(ordered.length * rowPx)}px` }}>
              {windowed.map((row, offset) => {
                const index = first + offset;
                const key = rowKey(row);
                const isSelected = selected.has(key);
                return (
                  <div
                    key={key}
                    role="row"
                    aria-rowindex={index + 2}
                    aria-selected={isSelected}
                    className={`absolute inset-x-0 grid items-center border-b border-line ${
                      isSelected ? 'bg-surface' : ''
                    }`}
                    style={{
                      gridTemplateColumns: template,
                      height: `${String(rowPx)}px`,
                      transform: `translateY(${String(index * rowPx)}px)`,
                    }}
                  >
                    <div role="cell" className="flex items-center px-3">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleRow(key)}
                        aria-label={`Select ${rowLabel?.(row) ?? key}`}
                      />
                    </div>
                    {visible.map((column) => (
                      <div
                        key={column.id}
                        role="cell"
                        className="truncate px-3 text-body-sm text-ink"
                      >
                        {column.cell(row)}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
