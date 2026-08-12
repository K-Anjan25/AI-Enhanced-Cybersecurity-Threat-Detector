import React, { useState, MouseEvent, ChangeEvent, ReactNode } from "react";


export interface Column<T = any> {
  id: string;
  label: string;
}

export interface TableRowData {
  id: string | number;
  [key: string]: any;
}

export interface RowDetailProps<T extends TableRowData = TableRowData> {
  row: T;
  columns: Column<T>[];
  onClickDetail?: (row: T) => void;
  renderDetailContent?: (row: T) => ReactNode;
}

export interface TableWithDetailProps<T extends TableRowData = TableRowData> {
  rows?: T[];
  columns?: Column<T>[];
  totalSize?: number;
  handleChangePage?: (event: unknown, newPage: number) => void;
  handleChangeItemsPerPage?: (newItemsPerPage: number) => void;
  itemsPerPage?: number;
  page?: number;
  onClickDetail?: (row: T) => void;
  renderDetailContent?: (row: T) => ReactNode;
}

function RowDetail<T extends TableRowData = TableRowData>({
  row,
  columns,
  onClickDetail,
  renderDetailContent,
}: RowDetailProps<T>) {
  const [open, setOpen] = useState<boolean>(false);

  const handleToggle = (e: MouseEvent): void => {
    e.stopPropagation();
    setOpen(!open);
    onClickDetail?.(row);
  };

  return (
    <>
      <tr
        onClick={handleToggle}
        className="hover:bg-app-subtle/50 transition cursor-pointer border-b border-line-subtle"
      >
        <td className="p-3 w-10 text-center">
          <button
            type="button"
            aria-label="expand row"
            onClick={handleToggle}
            className="p-1 hover:bg-app-subtle rounded text-content-tertiary hover:text-content-primary transition"
          >
            <span
              className={`inline-block transition-transform duration-200 ${
                open ? "rotate-180" : "rotate-0"
              }`}
            >
              ▼
            </span>
          </button>
        </td>
        {columns.map((column) => (
          <td key={column.id} className="p-3 text-content-secondary">
            {row[column.id]}
          </td>
        ))}
      </tr>

      {/* Collapsible Detail Drawer */}
      {open && (
        <tr className="bg-app-bg/40 border-b border-line-subtle">
          <td colSpan={columns.length + 1} className="p-4">
            {renderDetailContent ? (
              renderDetailContent(row)
            ) : (
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-content-tertiary">
                  Row Details
                </h4>
                <pre className="bg-app-bg p-3 rounded-lg text-xs font-mono text-content-secondary overflow-x-auto border border-line-subtle">
                  {JSON.stringify(row, null, 2)}
                </pre>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}


export default function TableWithDetail<T extends TableRowData = TableRowData>({
  rows = [],
  columns = [],
  totalSize = 0,
  handleChangePage,
  handleChangeItemsPerPage,
  itemsPerPage = 10,
  page = 0,
  onClickDetail,
  renderDetailContent,
}: TableWithDetailProps<T>) {
  return (
    <div className="w-full max-w-[1200px] mt-4 bg-app-surface text-content-primary rounded-lg border border-line-subtle overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-app-subtle text-content-secondary border-b border-line-subtle text-xs uppercase">
            <tr>
              <th className="p-3 w-10" />
              {columns.map((column) => (
                <th key={column.id} className="p-3 font-semibold">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <RowDetail
                key={row.id}
                row={row}
                columns={columns}
                onClickDetail={onClickDetail}
                renderDetailContent={renderDetailContent}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {page !== undefined && itemsPerPage && (
        <div className="flex items-center justify-between p-3 border-t border-line-subtle text-xs text-content-secondary">
          <div className="flex items-center gap-2">
            <span>Rows per page:</span>
            <select
              value={itemsPerPage}
              onChange={(e: ChangeEvent<HTMLSelectElement>) =>
                handleChangeItemsPerPage?.(Number(e.target.value))
              }
              className="bg-app-bg border border-line-subtle rounded px-2 py-1 text-content-primary focus:outline-none focus:border-accent-primary"
            >
              {[5, 10, 25].map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-4">
            <span>Total: {totalSize}</span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                disabled={page === 0}
                onClick={() => handleChangePage?.(null, page - 1)}
                className="px-2 py-1 bg-app-subtle hover:bg-line-bright disabled:opacity-40 disabled:hover:bg-app-subtle rounded transition"
              >
                Prev
              </button>
              <button
                type="button"
                disabled={(page + 1) * itemsPerPage >= totalSize}
                onClick={() => handleChangePage?.(null, page + 1)}
                className="px-2 py-1 bg-app-subtle hover:bg-line-bright disabled:opacity-40 disabled:hover:bg-app-subtle rounded transition"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
