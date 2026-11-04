import { useMemo, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react';
import { cx } from '@/lib/cx';
import { ICON } from '@/lib/icons';
import { formatNumber } from '@/lib/format';
import { SkeletonRows } from './Skeleton';
import { EmptyState } from './EmptyState';
import { Button } from './Button';

export type SortDir = 'asc' | 'desc';
export interface SortState {
  key: string;
  dir: SortDir;
}

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** Cell renderer. */
  render: (row: T, index: number) => ReactNode;
  /** Right-aligned tabular numbers. */
  numeric?: boolean;
  /** IBM Plex Mono for IDs, hashes, references. */
  mono?: boolean;
  sortable?: boolean;
  /** Client-side sort accessor (used only when onSortChange is not supplied). */
  sortValue?: (row: T) => string | number | null | undefined;
  width?: number | string;
  /** Plain-text header for aria-label when header is not text. */
  title?: string;
}

export interface PaginationState {
  page: number; // 1-based
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  loading?: boolean;
  emptyMessage?: ReactNode;
  emptyAction?: ReactNode;
  errorMessage?: ReactNode;
  /** Controlled sort. When onSortChange is given the caller sorts (server-side). */
  sort?: SortState | null;
  onSortChange?: (s: SortState | null) => void;
  /** Checkbox column for bulk actions. */
  selectable?: boolean;
  selectedKeys?: ReadonlySet<string>;
  onSelectionChange?: (keys: Set<string>) => void;
  pagination?: PaginationState;
  compact?: boolean;
  caption?: string;
  className?: string;
  /** max height of the scroll area (sticky header works inside it). */
  maxHeight?: number | string;
}

/** "1-25 of 612" */
export function paginationLabel(page: number, pageSize: number, total: number): string {
  if (total === 0) return '0 of 0';
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return `${formatNumber(from)}–${formatNumber(to)} of ${formatNumber(total)}`;
}

export function Pagination({ page, pageSize, total, onPageChange }: PaginationState) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex h-10 items-center justify-end gap-3 border-t border-line px-3 text-sm text-ink-500">
      <span className="tnum" aria-live="polite">
        {paginationLabel(page, pageSize, total)}
      </span>
      <Button variant="secondary" className="!h-7 !px-2" disabled={page <= 1} onClick={() => onPageChange(page - 1)} aria-label="Previous page">
        Previous
      </Button>
      <Button variant="secondary" className="!h-7 !px-2" disabled={page >= pages} onClick={() => onPageChange(page + 1)} aria-label="Next page">
        Next
      </Button>
    </div>
  );
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  selectedKey,
  loading,
  emptyMessage = 'No records match the current filters.',
  emptyAction,
  errorMessage,
  sort,
  onSortChange,
  selectable,
  selectedKeys,
  onSelectionChange,
  pagination,
  compact,
  caption,
  className,
  maxHeight,
}: DataTableProps<T>) {
  const [localSort, setLocalSort] = useState<SortState | null>(null);
  const active = onSortChange ? (sort ?? null) : localSort;

  const data = useMemo(() => {
    if (!rows) return rows;
    if (onSortChange || !active) return rows;
    const col = columns.find((c) => c.key === active.key);
    if (!col?.sortValue) return rows;
    const get = col.sortValue;
    const factor = active.dir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = get(a);
      const y = get(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * factor;
    });
  }, [rows, active, columns, onSortChange]);

  const toggleSort = (key: string) => {
    const next: SortState | null = !active || active.key !== key ? { key, dir: 'asc' } : active.dir === 'asc' ? { key, dir: 'desc' } : null;
    if (onSortChange) onSortChange(next);
    else setLocalSort(next);
  };

  const sel = selectedKeys ?? new Set<string>();
  const allSelected = !!data && data.length > 0 && data.every((r) => sel.has(rowKey(r)));
  const toggleAll = () => {
    if (!data || !onSelectionChange) return;
    onSelectionChange(allSelected ? new Set() : new Set(data.map(rowKey)));
  };
  const toggleOne = (k: string) => {
    if (!onSelectionChange) return;
    const n = new Set(sel);
    if (n.has(k)) n.delete(k);
    else n.add(k);
    onSelectionChange(n);
  };

  const colCount = columns.length + (selectable ? 1 : 0);

  return (
    <div className={cx('rounded border border-line bg-surface', className)}>
      <div className="overflow-auto" style={{ maxHeight }}>
        <table className={cx('ls-table', compact && 'compact')}>
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr>
              {selectable && (
                <th scope="col" style={{ width: 36 }}>
                  <input type="checkbox" aria-label="Select all rows" checked={allSelected} onChange={toggleAll} className="focus-ring h-3.5 w-3.5 accent-navy" />
                </th>
              )}
              {columns.map((c) => {
                const isActive = active?.key === c.key;
                const ariaSort = isActive ? (active!.dir === 'asc' ? 'ascending' : 'descending') : c.sortable ? 'none' : undefined;
                return (
                  <th key={c.key} scope="col" aria-sort={ariaSort} className={cx(c.numeric && 'num')} style={{ width: c.width, textAlign: c.numeric ? 'right' : undefined }}>
                    {c.sortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(c.key)}
                        className={cx('focus-ring inline-flex items-center gap-1 uppercase tracking-[0.04em]', c.numeric && 'flex-row-reverse')}
                        style={{ font: 'inherit', color: 'inherit', background: 'none', border: 0, padding: 0 }}
                      >
                        {c.header}
                        {isActive ? (
                          active!.dir === 'asc' ? (
                            <ChevronUp {...ICON} size={12} />
                          ) : (
                            <ChevronDown {...ICON} size={12} />
                          )
                        ) : (
                          <ChevronsUpDown {...ICON} size={12} className="text-ink-300" />
                        )}
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          {!loading && data && data.length > 0 && (
            <tbody>
              {data.map((row, i) => {
                const k = rowKey(row);
                return (
                  <tr
                    key={k}
                    className={cx(onRowClick && 'clickable')}
                    aria-selected={selectedKey === k || sel.has(k) || undefined}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                  >
                    {selectable && (
                      <td onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" aria-label="Select row" checked={sel.has(k)} onChange={() => toggleOne(k)} className="focus-ring h-3.5 w-3.5 accent-navy" />
                      </td>
                    )}
                    {columns.map((c) => (
                      <td key={c.key} className={cx(c.numeric && 'num', c.mono && 'id')}>
                        {c.render(row, i)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          )}
        </table>
        {loading && <SkeletonRows rows={compact ? 8 : 6} cols={Math.min(colCount, 6)} />}
        {!loading && errorMessage && <EmptyState tone="error" message={errorMessage} />}
        {!loading && !errorMessage && data && data.length === 0 && <EmptyState message={emptyMessage} action={emptyAction} />}
      </div>
      {pagination && <Pagination {...pagination} />}
    </div>
  );
}
