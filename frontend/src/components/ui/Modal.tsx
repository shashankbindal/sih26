import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { ICON } from '@/lib/icons';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}

/** Centered dialog for short confirmations and reason capture (e.g. PII reveal, reset demo). */
export function Modal({ open, onClose, title, children, footer, width = 480 }: ModalProps) {
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
    <div className="fixed inset-0 z-[60] flex items-start justify-center pt-[12vh]">
      <div className="anim-fade absolute inset-0" style={{ background: 'rgba(11, 27, 51, 0.32)' }} onClick={onClose} aria-hidden />
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        className="anim-fade relative max-w-[calc(100vw-32px)] rounded border border-line bg-surface shadow-menu outline-none"
        style={{ width }}
      >
        <header className="flex h-11 items-center justify-between border-b border-line px-4">
          <h2 className="text-md font-semibold text-ink-900">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="focus-ring -mr-1 inline-flex h-7 w-7 items-center justify-center rounded text-ink-500 hover:bg-paper">
            <X {...ICON} />
          </button>
        </header>
        <div className="p-4 text-sm">{children}</div>
        {footer && <footer className="flex items-center justify-end gap-2 border-t border-line px-4 py-3">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}
