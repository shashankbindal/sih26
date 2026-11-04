import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useApiQuery } from '@/api/hooks';
import { errorMessage } from '@/api/client';
import type { Schemas } from '@/api/types';
import { BureauTag, LinkStatusTag, MaskedValue, RelationBadge, StatusTag } from '@/components/domain';
import { ButtonLink, Drawer, EmptyState, Skeleton } from '@/components/ui';
import {
  CATEGORY_LABEL,
  CHANNEL_LABEL,
  PENDING_STEP_LABEL,
  type Bureau,
  type CaseCategory,
  type CaseStatus,
  type LinkStatus,
  type PendingStep,
  type RelationType,
  type SourceChannel,
} from '@/lib/constants';
import { formatDate, formatDateTime, formatDateTimeShort, shortHash } from '@/lib/format';
import { ClockPills, MaybeHindi, type CaseDetail } from './shared';
import { describeEvent } from '../passport/describe';

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-3 py-1.5 text-sm">
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className="m-0 min-w-0 text-ink-900">{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="label-caps mb-1.5">{title}</h3>
      {children}
    </section>
  );
}

export interface CaseQuickViewProps {
  caseId: string | null;
  onClose: () => void;
}

/** Right drawer from the case register: summary, clocks, links, last 3 Passport entries, Open case. */
export function CaseQuickView({ caseId, onClose }: CaseQuickViewProps) {
  const open = caseId !== null;
  const detail = useApiQuery<CaseDetail>(['case', caseId], `/cases/${caseId}`, { enabled: open });
  const passport = useApiQuery<Schemas['PassportOut']>(['passport', 'quick', caseId], `/cases/${caseId}/passport`, { enabled: open });
  const c = detail.data;
  const last3 = [...(passport.data?.entries ?? [])].sort((a, b) => b.seq - a.seq).slice(0, 3);
  const complainantMasked = !!c?.masked_fields.includes('complainant.name');

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={<span className="font-mono tnum">{c?.display_id ?? 'Case'}</span>}
      subtitle={c ? `Received ${formatDateTime(c.received_at)} · ${CHANNEL_LABEL[c.source_channel as SourceChannel] ?? c.source_channel}` : undefined}
      footer={
        caseId && (
          <ButtonLink variant="primary" to={`/cases/${caseId}`}>
            Open case
          </ButtonLink>
        )
      }
    >
      {detail.isLoading && (
        <div className="flex flex-col gap-3" role="status" aria-label="Loading">
          <Skeleton width="70%" height={18} />
          <Skeleton height={12} />
          <Skeleton width="85%" height={12} />
          <Skeleton height={12} />
        </div>
      )}
      {detail.isError && <EmptyState tone="error" message={`This case could not be loaded. ${errorMessage(detail.error)}`} />}
      {c && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <StatusTag status={c.status as CaseStatus} />
            <span className="text-xs text-ink-500">{CATEGORY_LABEL[c.category as CaseCategory] ?? c.category}</span>
          </div>
          <h3 className="mt-2 text-md font-semibold leading-snug text-ink-900">
            <MaybeHindi text={c.subject} />
          </h3>

          <dl className="m-0 mt-3 divide-y divide-line-soft border-y border-line-soft">
            <Row label="Institution">
              {c.institution ? (
                <>
                  <Link to={`/institutions/${c.institution.id}`}>{c.institution.name}</Link>
                  <div className="font-mono text-xs tnum text-ink-500">{c.institution.permanent_id}</div>
                </>
              ) : (
                <span className="text-ink-500">Unresolved{c.institution_text_raw ? ` · as written: ${c.institution_text_raw}` : ''}</span>
              )}
            </Row>
            <Row label="Owner">
              <span className="inline-flex flex-wrap items-center gap-x-2">
                <BureauTag bureau={c.owner_bureau as Bureau} roCode={c.owner_ro_code} />
                {c.owner_officer && <span className="text-ink-700">{c.owner_officer.name}</span>}
              </span>
            </Row>
            <Row label="Pending step">
              {PENDING_STEP_LABEL[c.pending_step as PendingStep] ?? c.pending_step}
              {c.pending_since && c.pending_step !== 'NONE' && <span className="text-ink-500"> · since {formatDate(c.pending_since)}</span>}
            </Row>
            <Row label="Complainant">
              {complainantMasked ? <MaskedValue ownerBureau={c.owner_bureau} /> : <span>{c.complainant.name ?? '–'}</span>}
            </Row>
          </dl>

          <Section title="Policy clocks">
            {c.clocks.length === 0 ? (
              <p className="m-0 text-sm text-ink-500">No policy clock applies to this case.</p>
            ) : (
              <ul className="m-0 list-none p-0">
                {c.clocks.map((k) => (
                  <li key={k.clock} className="flex items-center justify-between gap-3 border-b border-line-soft py-1.5 text-sm last:border-b-0">
                    <span className="text-ink-700">{k.long_label}</span>
                    <ClockPills clocks={[k]} />
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title={`Linked cases (${c.links.length})`}>
            {c.links.length === 0 ? (
              <p className="m-0 text-sm text-ink-500">No links on this case.</p>
            ) : (
              <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                {c.links.map((l) => (
                  <li key={l.id} className="flex flex-wrap items-center gap-2 text-sm">
                    <RelationBadge relation={l.relation as RelationType} />
                    <Link to={`/cases/${l.other_case.id}`} className="font-mono text-xs tnum">
                      {l.other_case.display_id}
                    </Link>
                    <BureauTag bureau={l.other_case.owner_bureau as Bureau} />
                    <LinkStatusTag status={l.status as LinkStatus} />
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Latest Passport entries">
            {passport.isLoading && <Skeleton height={36} />}
            {passport.isError && <p className="m-0 text-sm text-red">Passport unavailable. {errorMessage(passport.error)}</p>}
            {!passport.isLoading && !passport.isError && last3.length === 0 && <p className="m-0 text-sm text-ink-500">No entries recorded.</p>}
            <ol className="m-0 list-none p-0">
              {last3.map((e) => {
                const d = describeEvent(e.event, e.payload);
                return (
                  <li key={e.seq} className="border-b border-line-soft py-1.5 text-sm last:border-b-0">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-semibold text-ink-900">{d.label}</span>
                      <span className="font-mono text-xs tnum text-ink-500">{shortHash(e.hash)}</span>
                    </div>
                    <div className="text-xs text-ink-500">
                      {e.actor_name} · {formatDateTimeShort(e.created_at)}
                    </div>
                    {d.summary && <div className="mt-0.5 text-xs text-ink-700">{d.summary}</div>}
                  </li>
                );
              })}
            </ol>
          </Section>
        </>
      )}
    </Drawer>
  );
}
