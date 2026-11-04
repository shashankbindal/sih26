import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { ICON } from '@/lib/icons';
import { cx } from '@/lib/cx';

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  /** Default 560px (case quick view, link compare). */
  width?: number;
  className?: string;
}

/** Right-side drawer, 560px. Drawers and menus are the only elements with a shadow. */
export function Drawer({ open, onClose, title, subtitle, children, footer, width = 560, className }: DrawerProps) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50">
      <div className="anim-fade absolute inset-0" style={{ background: 'rgba(11, 27, 51, 0.32)' }} onClick={onClose} aria-hidden />
      <aside
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        className={cx('anim-drawer absolute inset-y-0 right-0 flex max-w-full flex-col border-l border-line bg-surface shadow-menu outline-none', className)}
        style={{ width }}
      >
        <header className="flex min-h-[52px] items-start justify-between gap-3 border-b border-line px-4 py-2.5">
          <div className="min-w-0">
            <h2 className="truncate text-md font-semibold text-ink-900">{title}</h2>
            {subtitle && <div className="mt-0.5 text-xs text-ink-500">{subtitle}</div>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="focus-ring -mr-1 inline-flex h-7 w-7 items-center justify-center rounded text-ink-500 hover:bg-paper">
            <X {...ICON} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
        {footer && <footer className="flex items-center justify-end gap-2 border-t border-line px-4 py-3">{footer}</footer>}
      </aside>
    </div>,
    document.body,
  );
}
