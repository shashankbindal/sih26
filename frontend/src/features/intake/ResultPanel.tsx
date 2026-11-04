import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Schemas } from '@/api/types';
import { useApiMutation } from '@/api/hooks';
import { BureauTag, ClockPill, InstitutionCard, LinkStatusTag, MatchStatusTag, ReasonList, RelationBadge } from '@/components/domain';
import { Badge, Button, ButtonLink, Panel, Select, useToast } from '@/components/ui';
import { CATEGORY_LABEL, MATCH_STATUS_LABEL, type Bureau, type CaseCategory, type LinkStatus, type MatchStatus, type RelationType } from '@/lib/constants';
import { formatScore } from '@/lib/format';
import {
  InlineError,
  LinkButton,
  LinkDecisionModal,
  MaybeHindi,
  ScoreBar,
  errText,
  type CaseCreateResult,
  type CreatedLink,
  type LinkDecisionKind,
  type ResolutionCandidate,
  type ResolutionOut,
} from './shared';

type InstitutionMatchResult = Schemas['InstitutionMatchResult'];

interface InstView {
  id: string;
  name: string;
  permanent_id: string;
  district?: string | null;
  state?: string | null;
}

/** EXACT is split by how it was matched; other statuses use the shared labels. */
function StatusLabel({ status, via }: { status: MatchStatus; via?: string | null }) {
  if (status === 'EXACT') {
    const text = via === 'alias' ? 'Exact match via confirmed alias' : 'Permanent ID exact';
    return <Badge tone="ok">{text}</Badge>;
  }
  return <MatchStatusTag status={status} />;
}

function CandidateRow({ cand, onPick, picking, current }: { cand: ResolutionCandidate; onPick: () => void; picking: boolean; current: boolean }) {
  return (
    <li className="flex items-start gap-3 border-b border-line-soft py-2.5 last:border-b-0">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-sm font-semibold text-ink-900">{cand.name}</span>
          <span className="font-mono text-xs tnum text-ink-500">{cand.permanent_id}</span>
        </div>
        <div className="text-xs text-ink-500">{[cand.district, cand.state].filter(Boolean).join(', ')}</div>
        <div className="mt-1.5">
          <ReasonList reasons={cand.reasons.slice(0, 3)} />
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-2">
        <ScoreBar score={cand.score} width={96} />
        <Button className="!h-7" variant={current ? 'secondary' : 'primary'} onClick={onPick} loading={picking} disabled={current}>
          {current ? 'Selected' : 'Select this'}
        </Button>
      </div>
    </li>
  );
}

function InstitutionSection({
  caseId,
  resolution,
  links,
  onLinks,
}: {
  caseId: string;
  resolution: ResolutionOut;
  links: CreatedLink[];
  onLinks: (l: CreatedLink[]) => void;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [changing, setChanging] = useState(false);
  const [confirmed, setConfirmed] = useState<{ inst: InstView; alias: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const via = resolution.candidates[0]?.matched_via;
  const sel = resolution.selected;
  const shown: InstView | null = confirmed?.inst ?? (sel ? { id: sel.institution_id, name: sel.name, permanent_id: sel.permanent_id, district: sel.district, state: sel.state } : null);

  const confirm = useApiMutation<InstitutionMatchResult, string>(
    (institution_id) =>
      api.post<InstitutionMatchResult>(`/cases/${caseId}/institution-match`, {
        decision: 'CONFIRM',
        institution_id,
        reason: 'Institution confirmed by officer at intake',
      }),
    {
      onSuccess: (res) => {
        if (res.institution) {
          setConfirmed({ inst: { id: res.institution.id, name: res.institution.name, permanent_id: res.institution.permanent_id, district: res.institution.district, state: res.institution.state }, alias: res.alias_added ?? null });
        }
        const seen = new Set(links.map((l) => l.link_id));
        const fresh = res.links.filter((l) => !seen.has(l.link_id));
        if (fresh.length) onLinks([...links, ...fresh]);
        setChanging(false);
        setError(null);
        toast(res.alias_added ? 'Institution confirmed. Alias saved for future matches.' : 'Institution confirmed.', 'ok');
        void qc.invalidateQueries({ queryKey: ['cases'] });
        void qc.invalidateQueries({ queryKey: ['case'] });
        void qc.invalidateQueries({ queryKey: ['review'] });
        void qc.invalidateQueries({ queryKey: ['count'] });
      },
      onError: (e) => setError(errText(e)),
    },
  );

  const top5 = resolution.candidates.slice(0, 5);
  const alreadyConfirmed = !!confirmed;

  return (
    <Panel
      title="Institution"
      actions={
        <>
          {alreadyConfirmed ? <MatchStatusTag status="CONFIRMED" /> : <StatusLabel status={resolution.status} via={via} />}
        </>
      }
    >
      {shown ? (
        <InstitutionCard institution={shown}>
          {!alreadyConfirmed && resolution.candidates[0] && (
            <div className="flex flex-col gap-2">
              {sel && (
                <div className="flex items-center gap-3">
                  <span className="label-caps text-ink-500">Match score</span>
                  <ScoreBar score={sel.score} width={200} />
                </div>
              )}
              <div className="label-caps text-ink-500">Why this institution</div>
              <ReasonList reasons={resolution.candidates[0].reasons} />
            </div>
          )}
          {alreadyConfirmed && (
            <div className="text-sm text-ink-700">
              Confirmed by you.{' '}
              {confirmed?.alias ? (
                <span>
                  Alias saved: <MaybeHindi text={confirmed.alias} className="font-medium text-ink-900" />. The same text now matches this institution exactly.
                </span>
              ) : null}
            </div>
          )}
        </InstitutionCard>
      ) : (
        <p className="m-0 text-sm text-ink-700">
          No confident match. {MATCH_STATUS_LABEL[resolution.status]}: choose one of the suggested institutions below, or resolve it from the{' '}
          <Link to="/review">review queue</Link>.
        </p>
      )}

      {!alreadyConfirmed && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {sel && (
            <Button variant="primary" onClick={() => confirm.mutate(sel.institution_id)} loading={confirm.isPending && !changing}>
              Confirm
            </Button>
          )}
          {top5.length > 0 && (
            <Button onClick={() => setChanging((v) => !v)} aria-expanded={changing}>
              {changing ? 'Hide candidates' : 'Change'}
            </Button>
          )}
          {resolution.status === 'NEEDS_REVIEW' && <span className="text-xs text-ink-500">Review suggested: the officer confirms the institution.</span>}
        </div>
      )}
      {error && <div className="mt-2"><InlineError>{error}</InlineError></div>}

      {changing && !alreadyConfirmed && (
        <div className="mt-3 rounded border border-line">
          <div className="border-b border-line bg-paper px-3 py-1.5 label-caps text-ink-500">Top {top5.length} candidates</div>
          <ul className="m-0 list-none px-3 py-0">
            {top5.map((c) => (
              <CandidateRow key={c.institution_id} cand={c} current={sel?.institution_id === c.institution_id} picking={confirm.isPending && confirm.variables === c.institution_id} onPick={() => confirm.mutate(c.institution_id)} />
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

function CategorySection({ caseId, suggestion, current }: { caseId: string; suggestion: CaseCreateResult['category_suggestion']; current: CaseCategory }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [value, setValue] = useState<CaseCategory>(current);
  const [error, setError] = useState<string | null>(null);
  const save = useApiMutation<unknown, CaseCategory>((category) => api.patch(`/cases/${caseId}`, { category }), {
    onSuccess: () => {
      toast('Category updated.', 'ok');
      void qc.invalidateQueries({ queryKey: ['case'] });
      void qc.invalidateQueries({ queryKey: ['cases'] });
    },
    onError: (e) => setError(errText(e)),
  });
  const suggested = suggestion.category as CaseCategory;
  return (
    <Panel title="Category">
      <p className="m-0 text-sm text-ink-700">
        Suggested: <span className="font-semibold text-ink-900">{CATEGORY_LABEL[suggested]}</span>
        {suggestion.keywords.length > 0 && <span className="text-ink-500"> (keywords: {suggestion.keywords.join(', ')})</span>}
      </p>
      <div className="mt-2 flex items-center gap-2">
        <label htmlFor="cat-sel" className="text-xs font-medium text-ink-700">
          Category on the case
        </label>
        <Select
          id="cat-sel"
          className="!w-56"
          value={value}
          onChange={(e) => {
            const v = e.target.value as CaseCategory;
            setValue(v);
            setError(null);
            save.mutate(v);
          }}
        >
          {(Object.keys(CATEGORY_LABEL) as CaseCategory[]).map((k) => (
            <option key={k} value={k}>
              {CATEGORY_LABEL[k]}
            </option>
          ))}
        </Select>
      </div>
      {error && <div className="mt-2"><InlineError>{error}</InlineError></div>}
    </Panel>
  );
}

const COORD: RelationType[] = ['RELATED', 'CONFLICTING'];

function LinkCard({ link, status, onDecide }: { link: CreatedLink; status: LinkStatus; onDecide: (d: LinkDecisionKind) => void }) {
  const [all, setAll] = useState(false);
  const reasons = all ? link.reasons : link.reasons.slice(0, 3);
  const rel = link.relation as RelationType;
  const coordination = COORD.includes(rel);
  const final = status === 'REJECTED' || status === 'SUPERSEDED';
  return (
    <li
      className="border-b border-line-soft last:border-b-0"
    >
      <div className={`flex gap-3 border-l-[3px] px-3 py-3 ${coordination ? (rel === 'CONFLICTING' ? 'border-l-red' : 'border-l-saffron') : 'border-l-transparent'}`}>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <RelationBadge relation={rel} />
            <LinkStatusTag status={status} />
            <span className="text-xs text-ink-500">
              Score <span className="font-mono tnum text-ink-900">{formatScore(link.score)}</span>
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <Link to={`/cases/${link.other_case.id}`} className="font-mono tnum">
              {link.other_case.display_id}
            </Link>
            <BureauTag bureau={link.other_case.owner_bureau as Bureau} />
            <span className="min-w-0 truncate text-ink-700">
              <MaybeHindi text={link.other_case.subject} />
            </span>
          </div>
          {link.reasons.length > 0 && (
            <div className="mt-2">
              <ReasonList reasons={reasons} numbered />
              {link.reasons.length > 3 && (
                <div className="mt-1">
                  <LinkButton onClick={() => setAll((v) => !v)}>{all ? 'Show fewer reasons' : `Show all ${link.reasons.length} reasons`}</LinkButton>
                </div>
              )}
            </div>
          )}
          {link.suggested_next_action && (
            <p className="m-0 mt-2 text-xs text-ink-500">
              <span className="font-medium text-ink-700">Suggested next action:</span> {link.suggested_next_action}
            </p>
          )}
        </div>
        {!final && (
          <div className="flex w-[96px] shrink-0 flex-col gap-1.5">
            <Button variant="primary" className="!h-7" disabled={status === 'CONFIRMED'} onClick={() => onDecide('CONFIRM')}>
              Confirm
            </Button>
            <Button className="!h-7" onClick={() => onDecide('REJECT')}>
              Reject
            </Button>
            <Button className="!h-7" disabled={status === 'DEFERRED'} onClick={() => onDecide('DEFER')}>
              Defer
            </Button>
          </div>
        )}
      </div>
    </li>
  );
}

function RelatedSection({ links, unrelated }: { links: CreatedLink[]; unrelated: CaseCreateResult['unrelated'] }) {
  const [statuses, setStatuses] = useState<Record<string, LinkStatus>>({});
  const [deciding, setDeciding] = useState<{ link: CreatedLink; decision: LinkDecisionKind } | null>(null);
  const sorted = [...links].sort((a, b) => b.score - a.score);
  return (
    <Panel title={`Related cases found${links.length ? ` (${links.length})` : ''}`} padded={false}>
      {sorted.length === 0 ? (
        <p className="m-0 px-3 py-3 text-sm text-ink-500">No related, duplicate or conflicting cases found on this institution.</p>
      ) : (
        <ul className="m-0 list-none p-0">
          {sorted.map((l) => (
            <LinkCard key={l.link_id} link={l} status={statuses[l.link_id] ?? (l.status as LinkStatus)} onDecide={(d) => setDeciding({ link: l, decision: d })} />
          ))}
        </ul>
      )}
      {unrelated.length > 0 && (
        <div className="border-t border-line-soft px-3 py-2 text-xs text-ink-500">
          Checked and unrelated, no alert:{' '}
          {unrelated.map((u, i) => (
            <span key={u.other_case.id}>
              {i > 0 && ', '}
              <Link to={`/cases/${u.other_case.id}`} className="font-mono tnum">
                {u.other_case.display_id}
              </Link>{' '}
              ({u.other_case.owner_bureau})
            </span>
          ))}
          . Same institution, different issue.
        </div>
      )}
      {deciding && (
        <LinkDecisionModal
          linkId={deciding.link.link_id}
          label={deciding.link.other_case.display_id}
          decision={deciding.decision}
          onClose={() => setDeciding(null)}
          onDone={(res) => setStatuses((s) => ({ ...s, [deciding.link.link_id]: res.status as LinkStatus }))}
        />
      )}
    </Panel>
  );
}

/** Result of POST /cases: institution, category, related cases, clocks, link to the case. */
export function ResultPanel({ result, onReset }: { result: CaseCreateResult; onReset: () => void }) {
  const c = result.case;
  const [links, setLinks] = useState<CreatedLink[]>(result.links);
  return (
    <div className="flex flex-col gap-3" aria-live="polite">
      <div className="flex items-center justify-between rounded border border-ok bg-ok-bg px-3 py-2 text-sm text-ok">
        <span>
          Case saved: <Link to={`/cases/${c.id}`} className="font-mono font-semibold tnum">{c.display_id}</Link>
        </span>
        <Button className="!h-7" onClick={onReset}>
          New case
        </Button>
      </div>
      <InstitutionSection caseId={c.id} resolution={result.resolution} links={links} onLinks={setLinks} />
      <CategorySection caseId={c.id} suggestion={result.category_suggestion} current={c.category as CaseCategory} />
      <RelatedSection links={links} unrelated={result.unrelated} />
      <Panel title="Clocks started">
        {result.clocks.length === 0 ? (
          <p className="m-0 text-sm text-ink-500">No clock applies to this channel.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {result.clocks.map((k) => (
              <ClockPill key={k.clock} label={k.label} state={k.state} clock={k.clock} clause={k.rule} />
            ))}
          </div>
        )}
      </Panel>
      <div>
        <ButtonLink to={`/cases/${c.id}`} variant="primary">
          Open case {c.display_id}
        </ButtonLink>
      </div>
    </div>
  );
}
