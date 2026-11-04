import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import { cx } from '@/lib/cx';

export interface TabItem {
  id: string;
  label: ReactNode;
  count?: number;
}

export interface TabsProps {
  tabs: TabItem[];
  value: string;
  onChange: (id: string) => void;
  className?: string;
  ariaLabel?: string;
}

/** Underlined tabs: 2px navy rule under the active tab, 1px line under the row. */
export function Tabs({ tabs, value, onChange, className, ariaLabel }: TabsProps) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const onKey = (e: KeyboardEvent, idx: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const next = tabs[(idx + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    onChange(next.id);
    refs.current[next.id]?.focus();
  };
  return (
    <div role="tablist" aria-label={ariaLabel} className={cx('flex gap-5 border-b border-line', className)}>
      {tabs.map((t, i) => {
        const active = t.id === value;
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            role="tab"
            type="button"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(t.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={cx(
              'focus-ring -mb-px inline-flex h-9 items-center gap-1.5 border-b-2 text-sm',
              active ? 'border-navy font-semibold text-ink-900' : 'border-transparent text-ink-500 hover:text-ink-900',
            )}
          >
            {t.label}
            {t.count !== undefined && <span className="tnum text-xs text-ink-500">{t.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
