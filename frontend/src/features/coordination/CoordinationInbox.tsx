import { useState } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftRight } from 'lucide-react';
import type { Schemas } from '@/api/types';
import { useApiQuery, useCount } from '@/api/hooks';
import { useAuth } from '@/auth';
import { BureauTag, LinkStatusTag, RelationBadge } from '@/components/domain';
import { DataTable, Tabs, type Column } from '@/components/ui';
import { type Bureau, type LinkStatus, type RelationType } from '@/lib/constants';
import { ageShort, formatScore } from '@/lib/format';
import { ICON } from '@/lib/icons';
import { PageHeader, errText } from '@/features/intake/shared';

type LinkPage = Schemas['LinkListPage'];
type LinkItem = Schemas['LinkListItem'];

type TabId = 'needs' | 'bureau' | 'open' | 'decided';
const OPEN = ['SUGGESTED', 'DEFERRED'];
const DECIDED = ['CONFIRMED', 'REJECTED'];
const PAGE_SIZE = 25;

function tabParams(tab: TabId, bureau: Bureau | undefined): Record<string, string | number | boolean | string[]> {
  switch (tab) {
    case 'needs':
      return { needs_my_decision: true };
    case 'bureau':
      return { status: OPEN, ...(bureau && bureau !== 'ADMIN' ? { bureau } : {}) };
    case 'open':
      return { status: OPEN };
    case 'decided':
      return { status: DECIDED };
  }
}

function CaseCell({ c }: { c: LinkItem['case_a'] }) {
  return (
    <span className="flex min-w-0 flex-col gap-0.5" title={c.subject}>
      <span className="font-mono text-sm tnum text-ink-900">{c.display_id}</span>
      <BureauTag bureau={c.owner_bureau as Bureau} />
    </span>
  );
}

export default function CoordinationInbox() {
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const bureau = user?.bureau as Bureau | undefined;
  const [tab, setTab] = useState<TabId>('needs');
  const [page, setPage] = useState(1);

  const linkParam = sp.get('link');
  // Dashboard click-through: /coordination?relation=CONFLICTING narrows the list to one relation type.
  const relationParam = sp.get('relation');
  const q = useApiQuery<LinkPage>(['links', 'inbox', tab, relationParam], '/links', {
    params: { ...tabParams(tab, bureau), ...(relationParam ? { relation: [relationParam] } : {}), page, page_size: PAGE_SIZE },
  });
  const cNeeds = useCount('links-needs', '/links', { needs_my_decision: true });
  const cBureau = useCount('links-bureau', '/links', tabParams('bureau', bureau));
  const cOpen = useCount('links-open', '/links', { status: OPEN });
  const cDecided = useCount('links-decided', '/links', { status: DECIDED });

  // Notification links of the form /coordination?link=<id>.
  if (linkParam) return <Navigate to={`/coordination/${linkParam}`} replace />;

  const columns: Column<LinkItem>[] = [
    { key: 'rel', header: 'Relation', width: 150, render: (r) => <RelationBadge relation={r.relation as RelationType} /> },
    {
      key: 'inst',
      header: 'Institution',
      width: 200,
      render: (r) =>
        r.institution ? (
          <div className="flex flex-col">
            <span className="max-w-[180px] truncate font-medium text-ink-900" title={r.institution.name}>{r.institution.name}</span>
            <span className="font-mono text-xs tnum text-ink-500">{r.institution.permanent_id}</span>
          </div>
        ) : (
          <span className="text-ink-300">{'–'}</span>
        ),
    },
    {
      key: 'cases',
      header: 'Case A ↔ Case B',
      width: 330,
      render: (r) => (
        <div className="flex items-center gap-3">
          <CaseCell c={r.case_a} />
          <ArrowLeftRight {...ICON} className="shrink-0 text-ink-300" />
          <CaseCell c={r.case_b} />
        </div>
      ),
    },
    { key: 'score', header: 'Score', numeric: true, mono: true, width: 64, render: (r) => formatScore(r.score) },
    { key: 'reason', header: 'Top reason', render: (r) => <span className="line-clamp-2 whitespace-normal text-ink-700">{r.top_reason ?? ''}</span> },
    { key: 'age', header: 'Age', numeric: true, mono: true, width: 56, render: (r) => ageShort(r.created_at) },
    { key: 'status', header: 'Status', width: 96, render: (r) => <LinkStatusTag status={r.status as LinkStatus} /> },
  ];

  const changeTab = (id: string) => {
    setTab(id as TabId);
    setPage(1);
  };

  return (
    <div>
      <PageHeader
        title="Coordination inbox"
        subtitle="Suggested links between cases on the same institution. Each is advisory: confirm, reject or defer with a reason."
      />
      <Tabs
        ariaLabel="Coordination views"
        className="mb-3"
        tabs={[
          { id: 'needs', label: 'Needs my decision', count: cNeeds },
          { id: 'bureau', label: 'My bureau', count: cBureau },
          { id: 'open', label: 'All open', count: cOpen },
          { id: 'decided', label: 'Decided', count: cDecided },
        ]}
        value={tab}
        onChange={changeTab}
      />
      <DataTable
        caption="Suggested case links"
        columns={columns}
        rows={q.data?.items}
        rowKey={(r) => r.id}
        loading={q.isLoading}
        errorMessage={q.isError ? errText(q.error) : undefined}
        emptyMessage={tab === 'needs' ? 'No links are waiting for your decision.' : 'No links in this view.'}
        onRowClick={(r) => navigate(`/coordination/${r.id}`)}
        pagination={q.data ? { page, pageSize: PAGE_SIZE, total: q.data.total, onPageChange: setPage } : undefined}
      />
    </div>
  );
}
