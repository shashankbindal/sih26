import { useCallback, useState } from 'react';
import { ChevronDown, X } from 'lucide-react';
import { Popover } from '@/components/ui';
import { cx } from '@/lib/cx';
import { ICON } from '@/lib/icons';

export interface ChipOption {
  value: string;
  label: string;
}

const chipBase =
  'focus-ring inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded border px-2 text-xs font-medium';
const chipIdle = 'border-line bg-surface text-ink-700 hover:border-ink-300';
const chipActive = 'border-navy bg-navy-50 text-ink-900';

export interface FilterChipProps {
  label: string;
  options: ReadonlyArray<ChipOption>;
  value: string[];
  onChange: (next: string[]) => void;
  /** Single choice closes the panel on pick. */
  single?: boolean;
}

/** Compact filter chip: "Status: Any" opening a checklist; active chips show their selection and a clear control. */
export function FilterChip({ label, options, value, onChange, single }: FilterChipProps) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const active = value.length > 0;
  const labels = value.map((v) => options.find((o) => o.value === v)?.label ?? v);
  const summary = !active ? 'Any' : labels.length === 1 ? labels[0] : `${labels[0]} +${labels.length - 1}`;

  const toggle = (v: string) => {
    if (single) {
      onChange(value[0] === v ? [] : [v]);
      close();
      return;
    }
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  };

  return (
    <Popover
      open={open}
      onClose={close}
      role="listbox"
      label={label}
      panelClassName="min-w-[200px] max-h-[320px] overflow-y-auto py-1"
      trigger={
        <span className="inline-flex items-center">
          <button type="button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((o) => !o)} className={cx(chipBase, active ? chipActive : chipIdle, active && 'rounded-r-none border-r-0')}>
            <span className="text-ink-500">{label}:</span>
            <span className="max-w-[160px] truncate">{summary}</span>
            <ChevronDown {...ICON} size={12} />
          </button>
          {active && (
            <button type="button" aria-label={`Clear ${label} filter`} onClick={() => onChange([])} className={cx(chipBase, chipActive, 'rounded-l-none border-l border-l-line px-1.5')}>
              <X {...ICON} size={12} />
            </button>
          )}
        </span>
      }
    >
      <ul role="presentation" className="m-0 list-none p-0">
        {options.map((o) => {
          const checked = value.includes(o.value);
          return (
            <li key={o.value}>
              <button
                type="button"
                role="option"
                aria-selected={checked}
                onClick={() => toggle(o.value)}
                className="focus-ring flex h-8 w-full items-center gap-2 px-3 text-left text-sm text-ink-900 hover:bg-navy-50"
              >
                <span aria-hidden className={cx('inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center border text-2xs leading-none', checked ? 'border-navy bg-navy text-surface' : 'border-ink-300 bg-surface')}>
                  {checked ? (single ? '' : '✓') : ''}
                </span>
                {o.label}
              </button>
            </li>
          );
        })}
      </ul>
    </Popover>
  );
}

export interface ToggleChipProps {
  label: string;
  pressed: boolean;
  onChange: (next: boolean) => void;
  coordination?: boolean;
}

/** Boolean filter chip (Overdue, Has alert, Owner: me). */
export function ToggleChip({ label, pressed, onChange, coordination }: ToggleChipProps) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={() => onChange(!pressed)}
      className={cx(chipBase, pressed ? (coordination ? 'border-saffron bg-saffron-bg text-ink-900' : chipActive) : chipIdle)}
    >
      {label}
    </button>
  );
}
