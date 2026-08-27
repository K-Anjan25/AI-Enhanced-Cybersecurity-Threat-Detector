import React, { useState, ChangeEvent } from "react";
import Select from "../../ui/Select";

export interface Column<T = any> {
  id: string;
  label: string;
}

export interface TableRowData {
  id: string | number;
  [key: string]: any;
}

export interface TableWithActionProps<T extends TableRowData = TableRowData> {
  rows?: T[];
  columns?: Column<T>[];
  totalSize?: number;
  loading?: boolean;
  handleChangePage?: (event: unknown, newPage: number) => void;
  handleChangeItemsPerPage?: (newItemsPerPage: number) => void;
  itemsPerPage?: number;
  page?: number;
  onEdit?: (row: T) => void;
  onDelete?: (row: T) => void;
  onView?: (row: T) => void;
  onBatchDelete?: (selectedIds: (string | number)[]) => void;
}

export default function TableWithAction<T extends TableRowData = TableRowData>({
  rows = [],
  columns = [],
  totalSize = 0,
  loading = false,
  handleChangeItemsPerPage,
  itemsPerPage = 10,
  onEdit,
  onDelete,
  onView,
  onBatchDelete,
}: TableWithActionProps<T>) {
  const [selected, setSelected] = useState<(string | number)[]>([]);

  const handleSelectAllClick = (e: ChangeEvent<HTMLInputElement>): void => {
    if (e.target.checked && rows) {
      setSelected(rows.map((n) => n.id));
      return;
    }
    setSelected([]);
  };

  const handleRowClick = (id: string | number): void => {
    const selectedIndex = selected.indexOf(id);
    let newSelected: (string | number)[] = [];

    if (selectedIndex === -1) {
      newSelected = newSelected.concat(selected, id);
    } else {
      newSelected = selected.filter((item) => item !== id);
    }
    setSelected(newSelected);
  };

  const isSelected = (id: string | number): boolean => selected.indexOf(id) !== -1;

  return (
    <div className="w-full max-w-[1200px] mt-4 bg-app-surface text-content-primary rounded-2xl border border-line-subtle overflow-hidden shadow-card">
      {selected.length > 0 && (
        <div className="bg-accent-primary/10 border-b border-accent-primary/30 px-4 py-2 flex justify-between items-center text-sm font-medium">
          <span>{selected.length} row(s) selected</span>
          {onBatchDelete && (
            <button
              type="button"
              className="bg-status-critical/15 text-red-300 hover:bg-status-critical/25 border border-status-critical/30 text-xs px-3 py-1.5 rounded-lg transition"
              onClick={() => {
                onBatchDelete(selected);
                setSelected([]);
              }}
            >
              Delete Selected
            </button>
          )}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-app-subtle text-content-secondary border-b border-line-subtle text-xs uppercase">
            <tr>
              <th scope="col" className="p-3 w-10 text-center">
                <input
                  type="checkbox"
                  className="rounded border-line-subtle bg-app-bg text-accent-primary focus:ring-0"
                  checked={rows.length > 0 && selected.length === rows.length}
                  onChange={handleSelectAllClick}
                />
              </th>
              {columns.map((col) => (
                <th key={col.id} className="p-3 font-semibold">
                  {col.label}
                </th>
              ))}
              <th scope="col" className="p-3 text-right font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line-subtle">
            {loading ? (
              <tr>
                <td colSpan={columns.length ? columns.length + 2 : 5} className="p-6 text-center text-content-tertiary">
                  Loading data...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length ? columns.length + 2 : 5} className="p-6 text-center text-content-tertiary">
                  No records found.
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const checked = isSelected(row.id);
                return (
                  <tr key={row.id} className="hover:bg-app-subtle/50 transition">
                    <td className="p-3 text-center">
                      <input
                        type="checkbox"
                        className="rounded border-line-subtle bg-app-bg text-accent-primary focus:ring-0"
                        checked={checked}
                        onChange={() => handleRowClick(row.id)}
                      />
                    </td>
                    {columns.map((col) => (
                      <td key={col.id} className="p-3 text-content-secondary">
                        {row[col.id]}
                      </td>
                    ))}
                    <td className="p-3 text-right">
                      <div className="flex justify-end gap-2">
                        {onView && (
                          <button
                            type="button"
                            title="View Details"
                            onClick={() => onView(row)}
                            className="p-1 hover:bg-app-subtle rounded text-content-tertiary hover:text-content-primary transition"
                          >
                            👁️
                          </button>
                        )}
                        {onEdit && (
                          <button
                            type="button"
                            title="Edit Row"
                            onClick={() => onEdit(row)}
                            className="p-1 hover:bg-app-subtle rounded text-content-tertiary hover:text-content-primary transition"
                          >
                            ✏️
                          </button>
                        )}
                        {onDelete && (
                          <button
                            type="button"
                            title="Delete Row"
                            onClick={() => onDelete(row)}
                            className="p-1 hover:bg-app-subtle rounded text-status-critical hover:text-status-critical/80 transition"
                          >
                            🗑️
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="flex items-center justify-between p-3 border-t border-line-subtle text-xs text-content-secondary">
        <div className="flex items-center gap-2">
          <span>Rows per page:</span>
          <Select
            inline
            value={String(itemsPerPage)}
            onChange={(e: ChangeEvent<HTMLSelectElement>) =>
              handleChangeItemsPerPage?.(Number(e.target.value))
            }
            className="w-auto px-2.5 py-1 rounded-lg text-xs"
            options={[5, 10, 25].map((opt) => ({ value: String(opt), label: String(opt) }))}
          />
        </div>
        <span>Total: {totalSize}</span>
      </div>
    </div>
  );
}