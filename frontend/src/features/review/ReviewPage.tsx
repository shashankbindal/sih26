import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Schemas } from '@/api/types';
import { useApiMutation, useApiQuery } from '@/api/hooks';
import { BureauTag, ReasonList, RelationBadge } from '@/components/domain';
import { Badge, Button, EmptyState, Field, Input, Modal, Panel, Skeleton, useToast } from '@/components/ui';
import { CHANNEL_LABEL, type Bureau, type RelationType, type SourceChannel } from '@/lib/constants';
import { formatDateTime, formatScore } from '@/lib/format';
import { InlineError, MaybeHindi, PageHeader, ScoreBar, errText } from '@/features/intake/shared';

type ReviewQueue = Schemas['ReviewQueue'];
type ReviewItem = Schemas['ReviewItem'];
type Candidate = Schemas['ReviewCandidate'];
type MatchResult = Schemas['InstitutionMatchResult'];
type SearchResult = Schemas['SearchResult'];

type Pick = { kind: 'confirm'; institution_id: string; name: string } | { kind: 'create' };

/** After a decision: what was saved and the links found (stage B). */
function Outcome({ item, result }: { item: ReviewItem; result: MatchResult }) {
  return (
    <div className="flex flex-col gap-2 px-3 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="ok">{result.decision === 'CREATE_NEW' ? 'New institution created' : 'Institution confirmed'}</Badge>
        <span className="font-mono tnum">{item.display_id}</span>
        {result.institution && <span className="font-semibold text-ink-900">{result.institution.name}</span>}
        {result.institution && <span className="font-mono text-xs tnum text-ink-500">{result.institution.permanent_id}</span>}
      </div>
      {result.alias_added && (
        <p className="m-0 text-ink-700">
          Alias saved: <MaybeHindi text={result.alias_added} className="font-medium text-ink-900" />. The same text now resolves to this institution exactly.
        </p>
      )}
      <div>
        <div className="label-caps mb-1 text-ink-500">Links found {result.links.length ? `(${result.links.length})` : ''}</div>
        {result.links.length === 0 ? (
          <p className="m-0 text-ink-500">No related, duplicate or conflicting cases on this institution.</p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {result.links.map((l) => (
              <li key={l.link_id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <RelationBadge relation={l.relation as RelationType} />
                <Link to={`/cases/${l.other_case.id}`} className="font-mono tnum">
                  {l.other_case.display_id}
                </Link>
                <BureauTag bureau={l.other_case.owner_bureau as Bureau} />
                <span className="font-mono text-xs tnum text-ink-500">{formatScore(l.score)}</span>
                {l.reasons[0] && <span className="text-xs text-ink-500">{l.reasons[0]}</span>}
                <Link to={`/coordination/${l.link_id}`} className="text-xs">
                  Compare
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <Link to={`/cases/${item.case_id}`}>Open case {item.display_id}</Link>
      </div>
    </div>
  );
}

function SearchModal({ onClose, onChoose }: { onClose: () => void; onChoose: (id: string, name: string) => void }) {
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(q.trim()), 300);
    return () => window.clearTimeout(t);
  }, [q]);
  const res = useApiQuery<SearchResult>(['search', 'inst'], '/search', { params: { q: debounced }, enabled: debounced.length >= 2 });
  const items = res.data?.institutions ?? [];
  return (
    <Modal open onClose={onClose} title="Search institutions" width={560}>
      <Field label="Name, place or Permanent ID" hint="Hindi or English.">
        <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} />
      </Field>
      <div className="mt-3 max-h-72 overflow-y-auto rounded border border-line">
        {debounced.length < 2 && <EmptyState message="Type at least two characters." />}
        {debounced.length >= 2 && res.isLoading && <div className="p-3"><Skeleton height={14} /></div>}
        {debounced.length >= 2 && !res.isLoading && items.length === 0 && <EmptyState message="No institution found." />}
        <ul className="m-0 list-none p-0">
          {items.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-3 border-b border-line-soft px-3 py-2 last:border-b-0">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-ink-900">{i.name}</div>
                <div className="text-xs text-ink-500">
                  <span className="font-mono tnum">{i.permanent_id}</span>
                  {i.district ? ` · ${i.district}` : ''}
                </div>
              </div>
              <Button className="!h-7" variant="primary" onClick={() => onChoose(i.id, i.name)}>
                Confirm this
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </Modal>
  );
}

function CandidateCol({ rank, cand, active, onConfirm, busy }: { rank: number; cand: Candidate; active: boolean; onConfirm: () => void; busy: boolean }) {
  const [all, setAll] = useState(false);
  const reasons = all ? cand.reasons : cand.reasons.slice(0, 4);
  return (
    <div className={`flex min-w-0 flex-col rounded border ${active ? 'border-navy bg-navy-50' : 'border-line bg-surface'} p-3`}>
      <div className="flex items-start justify-between gap-2">
        <span className="rounded-sm bg-neutral-bg px-1.5 font-mono text-xs leading-5 tnum text-ink-700" title={`Press ${rank} to select`}>
          {rank}
        </span>
        <ScoreBar score={cand.score} width={100} />
      </div>
      <div className="mt-2 text-sm font-semibold leading-snug text-ink-900">{cand.name}</div>
      <div className="mt-0.5 text-xs text-ink-500">
        <span className="font-mono tnum text-ink-700">{cand.permanent_id}</span>
        {(cand.district || cand.state) && <span> · {[cand.district, cand.state].filter(Boolean).join(', ')}</span>}
      </div>
      <div className="mt-2 flex-1">
        <ReasonList reasons={reasons} />
        {cand.reasons.length > 4 && (
          <button type="button" onClick={() => setAll((v) => !v)} className="focus-ring mt-1 text-xs text-navy hover:underline" style={{ background: 'none', border: 0, padding: 0 }}>
            {all ? 'Show fewer' : `Show all ${cand.reasons.length}`}
          </button>
        )}
      </div>
      <Button className="mt-3" variant={active ? 'primary' : 'secondary'} onClick={onConfirm} loading={busy}>
        Confirm this
      </Button>
    </div>
  );
}

function ReviewCard({ item, focused, onFocus, onDone }: { item: ReviewItem; focused: boolean; onFocus: () => void; onDone: (r: MatchResult) => void }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [searching, setSearching] = useState(false);
  const [pending, setPending] = useState<Pick | null>(null);
  const [selected, setSelected] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<MatchResult | null>(null);

  const decide = useApiMutation<MatchResult, Pick>(
    (p) =>
      api.post<MatchResult>(
        `/cases/${item.case_id}/institution-match`,
        p.kind === 'create'
          ? { decision: 'CREATE_NEW', reason: 'None of the suggested institutions matches; new institution created from the text as written' }
          : { decision: 'CONFIRM', institution_id: p.institution_id, reason: 'Institution confirmed by officer from the review queue' },
      ),
    {
      onSuccess: (res) => {
        setOutcome(res);
        setError(null);
        setPending(null);
        toast(res.alias_added ? 'Institution confirmed. Alias saved.' : 'Institution decision recorded.', 'ok');
        for (const k of ['review', 'cases', 'case', 'count', 'institution', 'links']) void qc.invalidateQueries({ queryKey: [k] });
        onDone(res);
      },
      onError: (e) => {
        setError(errText(e));
        setPending(null);
      },
    },
  );

  const cands = item.candidates.slice(0, 3);
  const confirmIdx = useCallback(
    (i: number) => {
      const c = cands[i];
      if (!c || decide.isPending || outcome) return;
      const p: Pick = { kind: 'confirm', institution_id: c.institution_id, name: c.name };
      setPending(p);
      decide.mutate(p);
    },
    [cands, decide, outcome],
  );

  // 1/2/3 pick, N = none (create new). Only the focused card listens.
  useEffect(() => {
    if (!focused || outcome) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === '1' || e.key === '2' || e.key === '3') {
        const i = Number(e.key) - 1;
        if (cands[i]) setSelected(i);
      } else if (e.key === 'Enter') {
        confirmIdx(selected);
      } else if (e.key.toLowerCase() === 'n') {
        const p: Pick = { kind: 'create' };
        setPending(p);
        decide.mutate(p);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [focused, outcome, cands, selected, confirmIdx, decide]);

  const top = item.top_score;
  return (
    <Panel
      className={focused ? 'ring-1 ring-navy' : undefined}
      title={
        <span className="flex items-center gap-3">
          <Link to={`/cases/${item.case_id}`} className="font-mono tnum">
            {item.display_id}
          </Link>
          <BureauTag bureau={item.owner_bureau as Bureau} />
          <span className="text-xs font-normal text-ink-500">
            {CHANNEL_LABEL[item.source_channel as SourceChannel] ?? item.source_channel} · {formatDateTime(item.received_at)}
          </span>
        </span>
      }
      actions={<Badge tone="amber">Needs review{top != null ? ` · top ${top.toFixed(3)}` : ''}</Badge>}
      padded={false}
    >
      <div onMouseDown={onFocus} onFocusCapture={onFocus}>
        {outcome ? (
          <Outcome item={item} result={outcome} />
        ) : (
          <div className="grid gap-4 p-3" style={{ gridTemplateColumns: '300px minmax(0, 1fr)' }}>
            <div className="min-w-0">
              <div className="label-caps text-ink-500">Institution as written</div>
              <div className="mt-1 break-words text-md font-semibold leading-snug text-ink-900">
                <MaybeHindi text={item.institution_text_raw} />
                {!item.institution_text_raw && <span className="text-ink-500">Not provided</span>}
              </div>
              {item.normalised_text && (
                <div className="mt-2 text-xs text-ink-500">
                  Normalised: <span className="font-mono text-ink-700">{item.normalised_text}</span>
                </div>
              )}
              {item.permanent_id_raw && (
                <div className="mt-1 text-xs text-ink-500">
                  Permanent ID given: <span className="font-mono text-ink-700">{item.permanent_id_raw}</span>
                </div>
              )}
              <div className="mt-3 text-sm text-ink-700">
                <span className="text-xs text-ink-500">Subject: </span>
                <MaybeHindi text={item.subject} />
              </div>
              <div className="mt-4 flex flex-col items-start gap-2">
                <Button onClick={() => setSearching(true)}>Search institutions</Button>
                <Button
                  onClick={() => {
                    const p: Pick = { kind: 'create' };
                    setPending(p);
                    decide.mutate(p);
                  }}
                  loading={decide.isPending && pending?.kind === 'create'}
                >
                  None of these: create new
                </Button>
                <span className="text-xs text-ink-500">
                  Keys: <span className="font-mono">1</span> <span className="font-mono">2</span> <span className="font-mono">3</span> pick, <span className="font-mono">Enter</span> confirm, <span className="font-mono">N</span> none
                </span>
              </div>
            </div>
            <div className="grid min-w-0 gap-3" style={{ gridTemplateColumns: `repeat(${Math.max(1, cands.length)}, minmax(0, 1fr))` }}>
              {cands.length === 0 && <EmptyState message="No candidate institutions were found for this text." />}
              {cands.map((c, i) => (
                <CandidateCol
                  key={c.institution_id}
                  rank={i + 1}
                  cand={c}
                  active={focused && selected === i}
                  busy={decide.isPending && pending?.kind === 'confirm' && pending.institution_id === c.institution_id}
                  onConfirm={() => {
                    setSelected(i);
                    confirmIdx(i);
                  }}
                />
              ))}
            </div>
          </div>
        )}
        {error && <div className="px-3 pb-3"><InlineError>{error}</InlineError></div>}
      </div>
      {searching && (
        <SearchModal
          onClose={() => setSearching(false)}
          onChoose={(id, name) => {
            setSearching(false);
            const p: Pick = { kind: 'confirm', institution_id: id, name };
            setPending(p);
            decide.mutate(p);
          }}
        />
      )}
    </Panel>
  );
}

export default function ReviewPage() {
  const q = useQuery<ReviewQueue, Error>({
    queryKey: ['review', 'institution-matches'],
    queryFn: ({ signal }) => api.get<ReviewQueue>('/review/institution-matches', { signal }),
    refetchOnWindowFocus: false,
  });
  const [focus, setFocus] = useState<string | null>(null);
  // Keep decided cards visible (with their outcome) until the page is left or refreshed.
  const [kept, setKept] = useState<ReviewItem[]>([]);
  const live = q.data?.items ?? [];
  const items = (() => {
    const ids = new Set(live.map((i) => i.case_id));
    return [...live, ...kept.filter((k) => !ids.has(k.case_id))];
  })();
  const focusId = focus ?? items[0]?.case_id ?? null;

  return (
    <div>
      <PageHeader
        title="Institution match review"
        subtitle="Cases whose institution needs an officer decision. Confirming saves the text as an alias, so the same wording matches exactly next time."
        actions={<span className="text-sm text-ink-500 tnum">{q.data ? `${live.length} awaiting review` : ''}</span>}
      />
      {q.isLoading && (
        <div className="flex flex-col gap-3" role="status" aria-label="Loading review queue">
          <Skeleton height={190} />
          <Skeleton height={190} />
        </div>
      )}
      {q.isError && <InlineError>{errText(q.error)}</InlineError>}
      {!q.isLoading && !q.isError && items.length === 0 && (
        <div className="rounded border border-line bg-surface">
          <EmptyState message="No cases are waiting for an institution decision." action={<Link to="/cases/new">New case</Link>} />
        </div>
      )}
      <div className="flex flex-col gap-3">
        {items.map((it) => (
          <ReviewCard
            key={it.case_id}
            item={it}
            focused={focusId === it.case_id}
            onFocus={() => setFocus(it.case_id)}
            onDone={() => setKept((k) => (k.some((x) => x.case_id === it.case_id) ? k : [...k, it]))}
          />
        ))}
      </div>
    </div>
  );
}
