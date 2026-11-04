import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import type { Tone } from '@/lib/constants';
import { StatusSquare } from './Badge';

interface ToastItem {
  id: number;
  message: ReactNode;
  tone: Tone;
}
interface ToastApi {
  /** Shows a 4 s toast, bottom-right. */
  toast: (message: ReactNode, tone?: Tone) => void;
}

const Ctx = createContext<ToastApi>({ toast: () => undefined });
export const useToast = (): ToastApi => useContext(Ctx);

/** Bottom-right, ink-900 background, white text, 4 s, only a small status square as icon. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);
  const toast = useCallback((message: ReactNode, tone: Tone = 'neutral') => {
    const id = ++seq.current;
    setItems((cur) => [...cur.slice(-3), { id, message, tone }]);
    window.setTimeout(() => setItems((cur) => cur.filter((t) => t.id !== id)), 4000);
  }, []);
  const api = useMemo(() => ({ toast }), [toast]);
  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[80] flex flex-col items-end gap-2" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className="anim-toast pointer-events-auto flex max-w-[360px] items-center gap-2 rounded bg-ink-900 px-3 py-2 text-sm text-surface">
            <StatusSquare tone={t.tone === 'neutral' ? 'info' : t.tone} />
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
