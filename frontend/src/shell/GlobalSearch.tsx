import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { api } from '@/api/client';
import { ICON } from '@/lib/icons';
import { cx } from '@/lib/cx';
import type { CaseStatus } from '@/lib/constants';
import { StatusTag } from '@/components/domain/StatusTag';
import { FOCUS_SEARCH_EVENT } from './useShortcuts';

interface InstHit {
  id: string;
  permanent_id: string;
  name: string;
  district?: string | null;
}
interface CaseHit {
  id: string;
  display_id: string;
  subject: string;
  institution_name?: string | null;
  status: CaseStatus;
}
interface SearchResponse {
  institutions: InstHit[];
  cases: CaseHit[];
}

type Row = { kind: 'inst'; hit: InstHit } | { kind: 'case'; hit: CaseHit };

/** As-you-type unified search (Institutions, Cases). Enter with nothing highlighted goes to /cases?q=. */
export function GlobalSearch() {
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const listId = useId();
  const [text, setText] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(text.trim()), 200);
    return () => window.clearTimeout(t);
  }, [text]);

  useEffect(() => {
    const focus = () => {
      input.current?.focus();
      input.current?.select();
    };
    window.addEventListener(FOCUS_SEARCH_EVENT, focus);
    return () => window.removeEventListener(FOCUS_SEARCH_EVENT, focus);
  }, []);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  const q = useQuery<SearchResponse>({
    queryKey: ['search', debounced],
    queryFn: ({ signal }) => api.get<SearchResponse>('/search', { params: { q: debounced }, signal }),
    enabled: debounced.length >= 2,
    staleTime: 30_000,
    retry: false,
  });

  const rows: Row[] = [
    ...(q.data?.institutions ?? []).map((hit): Row => ({ kind: 'inst', hit })),
    ...(q.data?.cases ?? []).map((hit): Row => ({ kind: 'case', hit })),
  ];

  const go = (r: Row) => {
    setOpen(false);
    setText('');
    input.current?.blur();
    navigate(r.kind === 'inst' ? `/institutions/${r.hit.id}` : `/cases/${r.hit.id}`);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => Math.min(rows.length - 1, a + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(-1, a - 1));
    } else if (e.key === 'Escape') {
      setOpen(false);
      input.current?.blur();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (active >= 0 && rows[active]) go(rows[active]);
      else if (text.trim()) {
        setOpen(false);
        navigate(`/cases?q=${encodeURIComponent(text.trim())}`);
      }
    }
  };

  const showPanel = open && debounced.length >= 2;
  const idx = (kind: 'inst' | 'case', i: number) => (kind === 'inst' ? i : (q.data?.institutions.length ?? 0) + i);

  return (
    <div ref={box} className="relative w-[480px] max-w-full">
      <Search {...ICON} className="pointer-events-none absolute left-2.5 top-2 text-ink-300" />
      <input
        ref={input}
        type="search"
        role="combobox"
        aria-expanded={showPanel}
        aria-controls={listId}
        aria-label="Search institutions and cases"
        placeholder="Search institution, Permanent ID or case ID    ( / )"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        className="focus-ring h-ctl w-full rounded border border-line bg-paper pl-8 pr-2.5 text-sm placeholder:text-ink-300 hover:border-ink-300 focus:bg-surface"
      />
      {showPanel && (
        <div id={listId} role="listbox" className="anim-fade absolute left-0 right-0 top-full z-40 mt-1 max-h-[420px] overflow-y-auto rounded border border-line bg-surface shadow-menu">
          {q.isFetching && rows.length === 0 && <div className="px-3 py-2 text-sm text-ink-500">Searching{'…'}</div>}
          {!q.isFetching && q.isError && <div className="px-3 py-2 text-sm text-ink-500">Search is unavailable right now.</div>}
          {!q.isFetching && !q.isError && rows.length === 0 && <div className="px-3 py-2 text-sm text-ink-500">No institutions or cases match {'“'}{debounced}{'”'}.</div>}

          {(q.data?.institutions.length ?? 0) > 0 && (
            <div>
              <div className="label-caps border-b border-line-soft bg-paper px-3 py-1">Institutions</div>
              {q.data!.institutions.map((h, i) => (
                <button
                  key={h.id}
                  type="button"
                  role="option"
                  aria-selected={active === idx('inst', i)}
                  onMouseEnter={() => setActive(idx('inst', i))}
                  onClick={() => go({ kind: 'inst', hit: h })}
                  className={cx('flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left text-sm', active === idx('inst', i) && 'bg-navy-50')}
                >
                  <span className="min-w-0 truncate font-medium text-ink-900">{h.name}</span>
                  <span className="shrink-0 text-xs text-ink-500">
                    <span className="font-mono tnum">{h.permanent_id}</span>
                    {h.district ? ` · ${h.district}` : ''}
                  </span>
                </button>
              ))}
            </div>
          )}
          {(q.data?.cases.length ?? 0) > 0 && (
            <div>
              <div className="label-caps border-y border-line-soft bg-paper px-3 py-1">Cases</div>
              {q.data!.cases.map((h, i) => (
                <button
                  key={h.id}
                  type="button"
                  role="option"
                  aria-selected={active === idx('case', i)}
                  onMouseEnter={() => setActive(idx('case', i))}
                  onClick={() => go({ kind: 'case', hit: h })}
                  className={cx('flex w-full items-center gap-3 px-3 py-1.5 text-left text-sm', active === idx('case', i) && 'bg-navy-50')}
                >
                  <span className="shrink-0 font-mono text-xs tnum text-ink-700">{h.display_id}</span>
                  <span className="min-w-0 flex-1 truncate text-ink-900">
                    {h.subject}
                    {h.institution_name && <span className="text-ink-500"> {'·'} {h.institution_name}</span>}
                  </span>
                  <StatusTag status={h.status} />
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
