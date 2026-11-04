import { cloneElement, useId, useRef, useState, type ReactElement, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export interface TooltipProps {
  content: ReactNode;
  children: ReactElement<{ 'aria-describedby'?: string }>;
  disabled?: boolean;
}

/** Hover/focus tooltip, ink-900 flat box, positioned above the trigger via a portal (never clipped). */
export function Tooltip({ content, children, disabled }: TooltipProps) {
  const id = useId();
  const wrap = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const show = () => {
    const r = wrap.current?.getBoundingClientRect();
    if (r) setPos({ x: r.left + r.width / 2, y: r.top });
  };
  const hide = () => setPos(null);
  if (disabled || !content) return children;
  return (
    <span ref={wrap} className="inline-flex" onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      {cloneElement(children, { 'aria-describedby': pos ? id : undefined })}
      {pos &&
        createPortal(
          <div
            id={id}
            role="tooltip"
            className="pointer-events-none fixed z-[70] max-w-[280px] rounded-sm bg-ink-900 px-2 py-1 text-xs text-surface"
            style={{ left: pos.x, top: pos.y - 6, transform: 'translate(-50%, -100%)' }}
          >
            {content}
          </div>,
          document.body,
        )}
    </span>
  );
}
