import { useCallback, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { cx } from '@/lib/cx';
import { Popover } from './Popover';

export interface MenuItem {
  key: string;
  label: ReactNode;
  onSelect?: () => void;
  to?: string;
  danger?: boolean;
  disabled?: boolean;
  /** Draws a 1px rule above the item. */
  separator?: boolean;
  hint?: ReactNode;
}

export interface DropdownMenuProps {
  items: MenuItem[];
  /** Render the trigger; call toggle() on click. */
  trigger: (ctl: { open: boolean; toggle: () => void }) => ReactNode;
  align?: 'left' | 'right';
  width?: number;
  header?: ReactNode;
}

/** Action menu: 32px rows, 1px border, menu shadow. */
export function DropdownMenu({ items, trigger, align = 'left', width = 220, header }: DropdownMenuProps) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const close = useCallback(() => setOpen(false), []);
  return (
    <Popover
      open={open}
      onClose={close}
      align={align}
      role="menu"
      panelClassName="py-1"
      trigger={trigger({ open, toggle: () => setOpen((o) => !o) })}
    >
      <div style={{ width }}>
        {header && <div className="border-b border-line px-3 py-2">{header}</div>}
        {items.map((it) => (
          <button
            key={it.key}
            role="menuitem"
            type="button"
            disabled={it.disabled}
            onClick={() => {
              close();
              if (it.to) navigate(it.to);
              it.onSelect?.();
            }}
            className={cx(
              'focus-ring flex h-8 w-full items-center justify-between gap-3 px-3 text-left text-sm hover:bg-navy-50 disabled:opacity-50',
              it.separator && 'border-t border-line',
              it.danger ? 'text-red' : 'text-ink-900',
            )}
          >
            <span>{it.label}</span>
            {it.hint && <span className="text-xs text-ink-500">{it.hint}</span>}
          </button>
        ))}
      </div>
    </Popover>
  );
}
