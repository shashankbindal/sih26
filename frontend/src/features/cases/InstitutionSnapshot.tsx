import { Link } from 'react-router-dom';
import { useApiQuery } from '@/api/hooks';
import { errorMessage } from '@/api/client';
import type { Schemas } from '@/api/types';
import { BureauTag, StatusTag } from '@/components/domain';
import { EmptyState, Panel, Skeleton } from '@/components/ui';
import { BUREAUS, CATEGORY_LABEL, OPEN_STATUSES, type Bureau, type CaseCategory, type CaseStatus } from '@/lib/constants';
import { formatNumber } from '@/lib/format';
import { ClockPills } from './shared';

type Timeline = Schemas['InstitutionTimeline'];
type Detail = Schemas['InstitutionDetail'];

/** Right column of case detail: who else is acting on this institution, by bureau. */
export function InstitutionSnapshot({ institutionId, currentCaseId }: { institutionId: string | null | undefined; currentCaseId: string }) {
  const enabled = !!institutionId;
  const detail = useApiQuery<Detail>(['institution', institutionId], `/institutions/${institutionId}`, { enabled });
  const timeline = useApiQuery<Timeline>(['institution', institutionId, 'timeline'], `/institutions/${institutionId}/timeline`, { enabled });

  if (!institutionId) {
    return (
      <Panel title="Institution snapshot">
        <p className="m-0 text-sm text-ink-500">Resolve the institution to see other open matters.</p>
      </Panel>
    );
  }

  const others = (timeline.data?.items ?? []).filter((c) => c.id !== currentCaseId && OPEN_STATUSES.includes(c.status as CaseStatus));
  const byBureau = BUREAUS.map((b) => ({ bureau: b as Bureau, cases: others.filter((c) => c.owner_bureau === b) })).filter((g) => g.cases.length > 0);
  const s = detail.data?.summary;

  return (
    <Panel
      title="Institution snapshot"
      actions={
        <Link to={`/institutions/${institutionId}`} className="text-xs">
          Open Institution 360
        </Link>
      }
      padded={false}
    >
      {(detail.isLoading || timeline.isLoading) && (
        <div className="flex flex-col gap-2 p-3" role="status" aria-label="Loading">
          <Skeleton height={14} />
          <Skeleton width="80%" height={14} />
          <Skeleton height={14} />
        </div>
      )}
      {(detail.isError || timeline.isError) && <EmptyState tone="error" message={`The snapshot could not be loaded. ${errorMessage(detail.error ?? timeline.error)}`} />}
      {s && (
        <div className="flex border-b border-line text-center">
          {[
            { k: 'Open', v: s.open_total },
            { k: 'Overdue', v: s.overdue },
            { k: 'Alerts', v: s.open_alerts, coordination: true },
          ].map((m, i) => (
            <div key={m.k} className={`flex-1 px-2 py-2 ${i > 0 ? 'border-l border-line' : ''}`}>
              <div className="flex items-center justify-center gap-1 text-xs text-ink-500">
                {m.coordination && <span aria-hidden className="inline-block h-2 w-2 bg-saffron" />}
                {m.k}
              </div>
              <div className="text-md font-semibold tnum text-ink-900">{formatNumber(m.v)}</div>
            </div>
          ))}
        </div>
      )}
      {timeline.data && (
        <div className="px-3 py-2">
          <div className="label-caps mb-1">Other open matters</div>
          {byBureau.length === 0 ? (
            <p className="m-0 py-1 text-sm text-ink-500">No other bureau has an open matter on this institution.</p>
          ) : (
            byBureau.map((g) => (
              <div key={g.bureau} className="border-t border-line-soft py-2 first:border-t-0">
                <div className="mb-1 flex items-center justify-between">
                  <BureauTag bureau={g.bureau} />
                  <span className="font-mono text-xs tnum text-ink-500">{g.cases.length}</span>
                </div>
                <ul className="m-0 list-none p-0">
                  {g.cases.map((o) => (
                    <li key={o.id} className="py-1 text-sm">
                      <div className="flex items-center justify-between gap-2">
                        <Link to={`/cases/${o.id}`} className="font-mono text-xs tnum">
                          {o.display_id}
                        </Link>
                        <StatusTag status={o.status as CaseStatus} />
                      </div>
                      <div className="mt-0.5 text-xs text-ink-500">{CATEGORY_LABEL[o.category as CaseCategory] ?? o.category}</div>
                      {o.clocks.length > 0 && (
                        <div className="mt-1">
                          <ClockPills clocks={o.clocks} />
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      )}
    </Panel>
  );
}
