import { Link, useNavigate } from 'react-router-dom';
import { DataTable, type Column } from '@/components/ui';
import { RelationBadge, BureauTag } from '@/components/domain';
import type { Bureau, RelationType } from '@/lib/constants';
import { ageShort } from '@/lib/format';
import { useApiQuery } from '@/api/hooks';
import { errorMessage } from '@/api/client';
import { useAuth } from '@/auth';
import { ACTIVE_LINK_STATUSES } from './api';

// /links is the Coordination inbox endpoint (the API specification "Links"). Fields are read defensively because the
// list item schema is defined by the backend.
interface CaseRef {
  id?: string;
  display_id?: string;
  owner_bureau?: Bureau | string | null;
  owner_ro_code?: string | null;
  owner_officer?: string | null;
  owner_officer_name?: string | null;
}
export interface LinkItem {
  id: string;
  relation: RelationType;
  status?: string;
  score?: number;
  institution_id?: string;
  institution_name?: string | null;
  institution?: { id?: string; name?: string } | null;
  case_a?: CaseRef;
  case_b?: CaseRef;
  created_at?: string | null;
  updated_at?: string | null;
}

const RANK: Record<string, number> = { CONFLICTING: 0, DUPLICATE: 1, RELATED: 2 };

function BureauPair({ a, b }: { a?: CaseRef; b?: CaseRef }) {
  const one = (c?: CaseRef) => (c?.owner_bureau ? <BureauTag bureau={c.owner_bureau as Bureau} /> : <span className="text-ink-300">–</span>);
  return (
    <span className="inline-flex items-center gap-2">
      {one(a)}
      <span aria-hidden className="text-ink-300">
        ↔
      </span>
      {one(b)}
    </span>
  );
}

function ownerOf(l: LinkItem): string {
  const o = (c?: CaseRef) => c?.owner_officer_name ?? c?.owner_officer ?? null;
  const names = [o(l.case_a), o(l.case_b)].filter((x): x is string => !!x);
  return names.length ? names.join(' / ') : '–';
}

export function CoordinationAlertsTable({ query }: { query: Record<string, string | string[]> }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const canOpen = user?.role !== 'SENIOR_MGMT'; // senior management has read-only oversight, no coordination inbox
  const q = useApiQuery<{ items: LinkItem[]; total: number }>(['links', 'dashboard-alerts'], '/links', {
    params: { relation: ['CONFLICTING', 'DUPLICATE', 'RELATED'], status: ACTIVE_LINK_STATUSES, both_open: true, page_size: 200, ...query },
    refetchInterval: 60_000,
  });
  const sorted = q.data?.items ? [...q.data.items].sort((a, b) => (RANK[a.relation] ?? 9) - (RANK[b.relation] ?? 9)) : undefined;
  const rows = sorted;
  const total = q.data?.total;

  const columns: Column<LinkItem>[] = [
    { key: 'relation', header: 'Relation', render: (l) => <RelationBadge relation={l.relation} />, width: 150 },
    {
      key: 'institution',
      header: 'Institution',
      render: (l) => {
        const name = l.institution_name ?? l.institution?.name ?? '–';
        const id = l.institution_id ?? l.institution?.id;
        return id ? (
          <Link to={`/institutions/${id}`} onClick={(e) => e.stopPropagation()} className="block max-w-[220px] truncate text-ink-900" title={name}>
            {name}
          </Link>
        ) : (
          name
        );
      },
    },
    { key: 'bureaus', header: 'Bureaus', render: (l) => <BureauPair a={l.case_a} b={l.case_b} /> },
    { key: 'age', header: 'Age', numeric: true, render: (l) => ageShort(l.created_at ?? l.updated_at) },
    { key: 'owner', header: 'Owner', render: (l) => <span className="block max-w-[140px] truncate" title={ownerOf(l)}>{ownerOf(l)}</span> },
  ];

  return (
    <>
    <DataTable
      compact
      caption="Open coordination alerts"
      columns={columns}
      rows={rows}
      rowKey={(l) => l.id}
      loading={q.isLoading}
      errorMessage={q.error ? `Could not load coordination alerts. ${errorMessage(q.error)}` : undefined}
      emptyMessage="No coordination alerts need action."
      onRowClick={canOpen ? (l) => navigate(`/coordination/${l.id}`) : undefined}
      className="border-0"
      maxHeight={520}
    />
    {total !== undefined && (
      <p className="border-t border-line px-4 py-2 text-sm text-ink-500 tnum">
        {total} open alerts: links where both cases are open, conflicting first.
      </p>
    )}
    </>
  );
}
