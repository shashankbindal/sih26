import { X } from 'lucide-react';
import { Button, Select } from '@/components/ui';
import { BUREAUS, BUREAU_LABEL, CASE_STATUS_LABEL, CATEGORY_LABEL, type CaseCategory, type CaseStatus } from '@/lib/constants';
import { ICON } from '@/lib/icons';
import { PLAIN_STATUS } from './plain';
import { useRegionOptions } from './api';
import { DEFAULT_RANGE, RANGE_OPTIONS, useDashboardFilters, type RangeId } from './filters';

function Chip({ label, onRemove }: { label: string; onRemove?: () => void }) {
  return (
    <span className="inline-flex h-7 items-center gap-1.5 rounded bg-navy-50 pl-2.5 pr-1.5 text-sm font-medium text-ink-900">
      {label}
      {onRemove ? (
        <button type="button" onClick={onRemove} aria-label={`Remove filter ${label}`} className="focus-ring inline-flex h-5 w-5 items-center justify-center rounded text-ink-700 hover:bg-line">
          <X {...ICON} size={14} />
        </button>
      ) : (
        <span className="pr-1 text-xs text-ink-500">fixed</span>
      )}
    </span>
  );
}

/** One compact row of filters; active ones also show as removable chips underneath. */
export function FilterBar() {
  const { filters, roLocked, set, reset, isDefault } = useDashboardFilters();
  const regions = useRegionOptions();
  const regionName = (code: string) => regions.data?.find((r) => r.ro_code === code)?.city ?? regions.data?.find((r) => r.ro_code === code)?.name ?? code;
  const rangeLabel = RANGE_OPTIONS.find((r) => r.id === filters.range)?.label ?? '';

  const chips: { key: string; label: string; onRemove?: () => void }[] = [];
  if (filters.range !== DEFAULT_RANGE) chips.push({ key: 'range', label: rangeLabel, onRemove: () => set({ range: DEFAULT_RANGE }) });
  if (filters.bureau) chips.push({ key: 'bureau', label: `Bureau: ${BUREAU_LABEL[filters.bureau as keyof typeof BUREAU_LABEL] ?? filters.bureau}`, onRemove: () => set({ bureau: '' }) });
  if (filters.ro) chips.push({ key: 'ro', label: `Region: ${regionName(filters.ro)}`, onRemove: roLocked ? undefined : () => set({ ro: '' }) });
  if (filters.category) chips.push({ key: 'category', label: `Category: ${CATEGORY_LABEL[filters.category as CaseCategory] ?? filters.category}`, onRemove: () => set({ category: '' }) });
  if (filters.status) chips.push({ key: 'status', label: `Status: ${PLAIN_STATUS[filters.status as CaseStatus] ?? filters.status}`, onRemove: () => set({ status: '' }) });

  const sel = 'h-9 text-base';
  return (
    <section aria-label="Dashboard filters" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="label-caps mr-1">Filters</span>
        <label className="sr-only" htmlFor="f-range">
          Date range
        </label>
        <Select id="f-range" className={`${sel} !w-40`} value={filters.range} onChange={(e) => set({ range: e.target.value as RangeId })}>
          {RANGE_OPTIONS.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
            </option>
          ))}
        </Select>
        <label className="sr-only" htmlFor="f-bureau">
          Bureau
        </label>
        <Select id="f-bureau" className={`${sel} !w-36`} value={filters.bureau} onChange={(e) => set({ bureau: e.target.value })}>
          <option value="">All bureaus</option>
          {BUREAUS.filter((b) => b !== 'ADMIN').map((b) => (
            <option key={b} value={b}>
              {BUREAU_LABEL[b]}
            </option>
          ))}
        </Select>
        <label className="sr-only" htmlFor="f-region">
          Region
        </label>
        <Select
          id="f-region"
          className={`${sel} !w-44`}
          value={filters.ro}
          disabled={roLocked}
          title={roLocked ? 'Regional Office users see their own region only' : undefined}
          onChange={(e) => set({ ro: e.target.value })}
        >
          <option value="">All regions</option>
          {(regions.data ?? []).map((r) => (
            <option key={r.ro_code} value={r.ro_code}>
              {r.city ?? r.name}
            </option>
          ))}
        </Select>
        <label className="sr-only" htmlFor="f-category">
          Category
        </label>
        <Select id="f-category" className={`${sel} !w-44`} value={filters.category} onChange={(e) => set({ category: e.target.value })}>
          <option value="">All categories</option>
          {(Object.keys(CATEGORY_LABEL) as CaseCategory[]).map((c) => (
            <option key={c} value={c}>
              {CATEGORY_LABEL[c]}
            </option>
          ))}
        </Select>
        <label className="sr-only" htmlFor="f-status">
          Status
        </label>
        <Select id="f-status" className={`${sel} !w-48`} value={filters.status} onChange={(e) => set({ status: e.target.value })}>
          <option value="">All statuses</option>
          {(Object.keys(CASE_STATUS_LABEL) as CaseStatus[]).map((s) => (
            <option key={s} value={s}>
              {PLAIN_STATUS[s]}
            </option>
          ))}
        </Select>
        <Button variant="tertiary" className="px-1 text-base" onClick={reset} disabled={isDefault}>
          Reset
        </Button>
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" aria-label="Active filters">
          {chips.map((c) => (
            <Chip key={c.key} label={c.label} onRemove={c.onRemove} />
          ))}
        </div>
      )}
    </section>
  );
}
