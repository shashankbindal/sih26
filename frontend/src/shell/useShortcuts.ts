import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export const FOCUS_SEARCH_EVENT = 'ls:focus-search';

function isTyping(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}

/** `/` focuses global search; `g d` dashboard, `g c` cases, `g i` institutions. Ignored while typing. */
export function useGlobalShortcuts(): void {
  const navigate = useNavigate();
  useEffect(() => {
    let pendingG = 0;
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
      if (e.key === '/') {
        e.preventDefault();
        window.dispatchEvent(new Event(FOCUS_SEARCH_EVENT));
        return;
      }
      if (pendingG) {
        window.clearTimeout(pendingG);
        pendingG = 0;
        const dest: Record<string, string> = { d: '/', c: '/cases', i: '/institutions' };
        const to = dest[e.key.toLowerCase()];
        if (to) {
          e.preventDefault();
          navigate(to);
        }
        return;
      }
      if (e.key === 'g') pendingG = window.setTimeout(() => (pendingG = 0), 1000);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.clearTimeout(pendingG);
    };
  }, [navigate]);
}
