import { useEffect, useRef, type ReactNode } from 'react';
import { cx } from '@/lib/cx';

export interface PopoverProps {
  open: boolean;
  onClose: () => void;
  /** Element(s) that open the popover; clicks inside the wrapper do not count as outside. */
  trigger: ReactNode;
  children: ReactNode;
  align?: 'left' | 'right';
  className?: string;
  panelClassName?: string;
  /** role of the panel (menu, dialog, listbox). */
  role?: string;
  label?: string;
}

/** Anchored panel: 1px border + the single permitted menu shadow. Closes on outside click and Escape. */
export function Popover({ open, onClose, trigger, children, align = 'left', className, panelClassName, role = 'dialog', label }: PopoverProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);
  return (
    <div ref={ref} className={cx('relative', className)}>
      {trigger}
      {open && (
        <div
          role={role}
          aria-label={label}
          className={cx(
            'anim-fade absolute top-full z-40 mt-1 rounded border border-line bg-surface shadow-menu',
            align === 'right' ? 'right-0' : 'left-0',
            panelClassName,
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}
