import { useState, type ReactNode } from 'react';
import ReactECharts from 'echarts-for-react';
import { Download, Plus } from 'lucide-react';
import {
  Badge,
  Button,
  ButtonLink,
  Checkbox,
  DataTable,
  Drawer,
  DropdownMenu,
  EmptyState,
  Field,
  Input,
  KpiStrip,
  Modal,
  Panel,
  Select,
  Skeleton,
  SkeletonRows,
  Tabs,
  Textarea,
  Tooltip,
  useToast,
  type Column,
} from '@/components/ui';
import {
  BureauTag,
  ClockPill,
  ColdStartBanner,
  InstitutionCard,
  MaskedValue,
  PassportTimeline,
  ReasonList,
  RelationBadge,
  ScoreMeter,
  StatusTag,
  MatchStatusTag,
  LinkStatusTag,
  ClearanceTag,
  type ChainVerification,
  type PassportEntry,
} from '@/components/domain';
import { BUREAUS, type CaseStatus, type ClockState, type RelationType } from '@/lib/constants';
import { registerLoksutraTheme } from '@/lib/echartsTheme';
import { formatDateTime, formatNumber, formatRupee, relativeDays, shortHash } from '@/lib/format';

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h2 className="label-caps mb-2 border-b border-line pb-1">{title}</h2>
      {children}
    </section>
  );
}
const Row = ({ children }: { children: ReactNode }) => <div className="flex flex-wrap items-center gap-3">{children}</div>;

interface DemoRow {
  id: string;
  received: string;
  institution: string;
  open: number;
  overdue: number;
  status: CaseStatus;
}
const DEMO_ROWS: DemoRow[] = [
  { id: 'LS-2026-000612', received: '2026-11-01T09:42:00Z', institution: 'Shrinath Institute of Engineering & Technology', open: 5, overdue: 1, status: 'RECEIVED' },
  { id: 'LS-2026-000204', received: '2026-10-21T05:10:00Z', institution: 'Shrinath Institute of Engineering & Technology', open: 12, overdue: 4, status: 'AWAITING_ATR' },
  { id: 'LS-2026-000188', received: '2026-10-12T11:30:00Z', institution: 'Gomti Polytechnic College', open: 123456, overdue: 0, status: 'UNDER_PROCESS' },
  { id: 'LS-2026-000377', received: '2026-09-30T07:05:00Z', institution: 'Narmada Valley Institute of Management', open: 3, overdue: 2, status: 'ESCALATED' },
];

const ENTRIES: PassportEntry[] = [
  { seq: 1, event: 'Case received', actor_name: 'Ritu Sharma', bureau: 'PGRC', at: '2026-10-21T05:10:00Z', remark: 'Registered from CSS ticket.', hash: 'a3f9c4d2e8b71f0a6c5d9e2b4a7f3c21e8d0b5a6f1c2d3e4a5b6c7d8e9f0c21e' },
  { seq: 2, event: 'Institution matched', actor_name: 'System', bureau: 'PGRC', at: '2026-10-21T05:10:03Z', remark: 'Auto-suggested; confirmed by officer.', hash: '7be10f2a9c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5061728394a5b6d90' },
  { seq: 3, event: 'Marked awaiting institution ATR', actor_name: 'Ritu Sharma', bureau: 'PGRC', at: '2026-10-22T10:40:00Z', hash: 'c41d88e0aa11bb22cc33dd44ee55ff6600112233445566778899aabbccddee07' },
  { seq: 4, event: 'Link suggested', actor_name: 'System', bureau: 'PGRC', at: '2026-11-01T09:42:05Z', remark: 'Coordination required with RB case.', hash: '09ab34cd56ef78019a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f4f1e' },
];

const REASONS = [
  'Same district: Kanpur Nagar',
  'Name tokens match: shrinath, engineering, college — "SIET" is a confirmed alias',
  'Pincode 208017 matches the registered address',
  'Category differs, same institution',
];

const KIT_THRESHOLDS = { review: 0.75, auto: 0.92 }; // demo values for the kit only

const relations: RelationType[] = ['DUPLICATE', 'RELATED', 'CONFLICTING', 'UNRELATED'];
const clockSamples: Array<{ label: string; state: ClockState; clause?: string }> = [
  { label: '21-day · 14d left', state: 'ON_TRACK', clause: 'CPGRAMS disposal timeline' },
  { label: '21-day · 3d left', state: 'AMBER', clause: 'CPGRAMS disposal timeline' },
  { label: 'Inst. 7-day · overdue 4d', state: 'BREACHED', clause: 'APH 2024-27 cl. 6.45' },
  { label: '72-hour · paused', state: 'PAUSED', clause: 'Paused while awaiting complainant' },
  { label: '72-hour · met', state: 'MET', clause: 'CSS acknowledgement' },
];

export default function Kit() {
  const { toast } = useToast();
  const [tab, setTab] = useState('summary');
  const [drawer, setDrawer] = useState(false);
  const [modal, setModal] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  const [verification, setVerification] = useState<ChainVerification | null>(null);
  const theme = registerLoksutraTheme();

  const cols: Column<DemoRow>[] = [
    { key: 'id', header: 'Case ID', mono: true, sortable: true, sortValue: (r) => r.id, render: (r) => r.id },
    { key: 'received', header: 'Received', sortable: true, sortValue: (r) => r.received, render: (r) => formatDateTime(r.received) },
    { key: 'institution', header: 'Institution', render: (r) => r.institution },
    { key: 'status', header: 'Status', render: (r) => <StatusTag status={r.status} /> },
    { key: 'open', header: 'Open', numeric: true, sortable: true, sortValue: (r) => r.open, render: (r) => formatNumber(r.open) },
    { key: 'overdue', header: 'Overdue', numeric: true, sortable: true, sortValue: (r) => r.overdue, render: (r) => formatNumber(r.overdue) },
  ];

  const chart = {
    title: { text: 'Open cases by bureau and status', left: 0 },
    tooltip: { trigger: 'axis' as const },
    legend: { bottom: 0 },
    grid: { left: 8, right: 16, top: 32, bottom: 32, containLabel: true },
    xAxis: { type: 'value' as const },
    yAxis: { type: 'category' as const, data: BUREAUS.slice(0, 5), inverse: true },
    series: [
      { name: 'Received', type: 'bar' as const, stack: 's', data: [12, 5, 2, 1, 4] },
      { name: 'Under process', type: 'bar' as const, stack: 's', data: [18, 9, 3, 2, 6] },
      { name: 'Awaiting ATR', type: 'bar' as const, stack: 's', data: [9, 2, 0, 1, 2] },
    ],
  };

  return (
    <div className="min-h-full bg-paper">
      <div className="border-b border-line bg-surface px-6 py-3">
        <h1 className="text-xl font-semibold">Component kit</h1>
        <p className="text-sm text-ink-500">Every primitive and domain component in every state. Developer QA route, not linked in the nav.</p>
      </div>
      <div className="mx-auto max-w-[1280px] px-6 py-5">
        <Section title="Typography and tokens">
          <Row>
            <span className="text-xl font-semibold">Page title, sentence case</span>
            <span className="text-md font-semibold">Section title 16</span>
            <span className="text-base">Body 14</span>
            <span className="text-sm">Table body 13</span>
            <span className="text-xs text-ink-500">Meta 12</span>
            <span lang="hi">संस्थान · समन्वय · मामले</span>
            <span className="mono">LS-2026-000612 · 1-4463974255 · {shortHash('a3f9c4d2e8b71f0a6c5d9e2b4a7f3c21e8d0b5a6f1c2d3e4a5b6c7d8e9f0c21e')}</span>
            <span className="tnum">{formatRupee(85000)} · {formatNumber(123456)} · {relativeDays('2026-10-21T05:10:00Z', new Date('2026-11-01T10:00:00Z'))}</span>
          </Row>
          <div className="mt-3 flex flex-wrap gap-2">
            {['ink-900', 'ink-700', 'ink-500', 'ink-300', 'line', 'paper', 'navy', 'navy-50', 'ok', 'amber', 'red', 'info', 'neutral', 'saffron', 'saffron-bg'].map((t) => (
              <div key={t} className="w-[88px]">
                <div className="h-6 border border-line" style={{ background: `var(--${t})` }} />
                <div className="mt-0.5 font-mono text-2xs text-ink-500">{t}</div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Buttons">
          <Row>
            <Button variant="primary">Confirm link</Button>
            <Button variant="primary" icon={Plus}>New case</Button>
            <Button variant="primary" disabled>Disabled</Button>
            <Button variant="primary" loading>Saving</Button>
            <Button>Request PGRC clearance</Button>
            <Button icon={Download}>Export CSV</Button>
            <Button variant="tertiary">Show all reasons</Button>
            <Button variant="danger">Reset demo data</Button>
            <ButtonLink to="/cases">Router link as button</ButtonLink>
            <Tooltip content="Download CSV">
              <Button aria-label="Download CSV" icon={Download} />
            </Tooltip>
          </Row>
        </Section>

        <Section title="Badges and status tags">
          <Row>
            <Badge tone="ok">Disposed</Badge>
            <Badge tone="amber">Awaiting ATR</Badge>
            <Badge tone="red">Escalated</Badge>
            <Badge tone="info">Received</Badge>
            <Badge tone="neutral">Transferred</Badge>
          </Row>
          <div className="mt-2"><Row>
            {(['RECEIVED', 'UNDER_PROCESS', 'AWAITING_ATR', 'AWAITING_COMPLAINANT', 'TRANSFERRED', 'ESCALATED', 'DISPOSED', 'CLOSED_NO_ACTION', 'REOPENED'] as CaseStatus[]).map((s) => (
              <StatusTag key={s} status={s} />
            ))}
          </Row></div>
          <div className="mt-2"><Row>
            <MatchStatusTag status="EXACT" /><MatchStatusTag status="AUTO_SUGGESTED" /><MatchStatusTag status="NEEDS_REVIEW" /><MatchStatusTag status="UNRESOLVED" />
            <LinkStatusTag status="SUGGESTED" /><LinkStatusTag status="CONFIRMED" /><LinkStatusTag status="DEFERRED" />
            <ClearanceTag response="PENDING" /><ClearanceTag response="CLEARED" /><ClearanceTag response="NOT_CLEARED" /><ClearanceTag response="CLEARED_WITH_REMARKS" />
          </Row></div>
        </Section>

        <Section title="RelationBadge, ClockPill, BureauTag, ScoreMeter">
          <Row>{relations.map((r) => <RelationBadge key={r} relation={r} />)}</Row>
          <div className="mt-2"><Row>{clockSamples.map((c) => <ClockPill key={c.label} {...c} />)}</Row></div>
          <div className="mt-2"><Row>{BUREAUS.map((b) => <BureauTag key={b} bureau={b} roCode={b === 'RO' ? 'KNP' : null} />)}</Row></div>
          <div className="mt-3 flex flex-wrap items-start gap-8">
            <ScoreMeter score={0.94} thresholds={KIT_THRESHOLDS} />
            <ScoreMeter score={0.81} thresholds={KIT_THRESHOLDS} />
            <ScoreMeter score={0.48} thresholds={KIT_THRESHOLDS} />
          </div>
        </Section>

        <Section title="Panel, ReasonList, MaskedValue, InstitutionCard">
          <div className="grid grid-cols-2 gap-4">
            <Panel title="Why this institution" actions={<Button variant="tertiary">Show all</Button>}>
              <ReasonList reasons={REASONS} numbered />
            </Panel>
            <Panel title="Complainant">
              <dl className="m-0 grid grid-cols-[120px_1fr] gap-y-2 text-sm">
                <dt className="text-ink-500">Name</dt>
                <dd className="m-0"><MaskedValue ownerBureau="PGRC" onRequestAccess={() => toast('Access request opens a reason dialog.', 'info')} /></dd>
                <dt className="text-ink-500">Phone</dt>
                <dd className="m-0"><MaskedValue ownerBureau="PGRC" /></dd>
                <dt className="text-ink-500">Party type</dt>
                <dd className="m-0">Student</dd>
              </dl>
            </Panel>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-4">
            <InstitutionCard
              institution={{ id: 'x1', name: 'Shrinath Institute of Engineering & Technology', permanent_id: '1-4463974255', district: 'Kanpur Nagar', state: 'Uttar Pradesh', pincode: '208017', ro_name: 'Kanpur', institution_type: 'Engineering', approval_status: 'Approved' }}
              aside={<ScoreMeter score={0.94} thresholds={KIT_THRESHOLDS} />}
            >
              <ReasonList reasons={REASONS.slice(0, 2)} />
            </InstitutionCard>
            <InstitutionCard institution={{ id: 'x2', name: 'Gomti Polytechnic College', permanent_id: '1-5120098431', district: 'Lucknow', state: 'Uttar Pradesh', approval_status: 'Closure under review' }} linked={false} />
          </div>
        </Section>

        <Section title="KpiStrip (loaded, loading)">
          <KpiStrip
            items={[
              { key: 'total', label: 'Total', value: 1234, delta: 18, to: '/cases' },
              { key: 'pending', label: 'Pending', value: 612, delta: -24, deltaGoodWhen: 'down' },
              { key: 'under', label: 'Under process', value: 301, delta: 0 },
              { key: 'disposed', label: 'Disposed', value: 241 },
              { key: 'overdue', label: 'Overdue by policy', value: 57, delta: 6, deltaGoodWhen: 'down' },
              { key: 'alerts', label: 'Open coordination alerts', value: 14, coordination: true, onClick: () => toast('Filtered to coordination alerts.', 'info') },
            ]}
          />
          <div className="mt-3"><KpiStrip loading items={[{ key: 'a', label: 'Total', value: 0 }, { key: 'b', label: 'Pending', value: 0 }, { key: 'c', label: 'Disposed', value: 0 }]} /></div>
        </Section>

        <Section title="Table: data, selection, sort, pagination / loading / empty / error">
          <DataTable
            caption="Demo cases"
            columns={cols}
            rows={DEMO_ROWS}
            rowKey={(r) => r.id}
            selectable
            selectedKeys={selected}
            onSelectionChange={setSelected}
            onRowClick={() => setDrawer(true)}
            pagination={{ page, pageSize: 25, total: 612, onPageChange: setPage }}
          />
          <div className="mt-3 grid grid-cols-3 gap-4">
            <DataTable columns={cols.slice(0, 3)} rows={undefined} loading rowKey={(r) => r.id} />
            <DataTable columns={cols.slice(0, 3)} rows={[]} rowKey={(r) => r.id} emptyMessage="No open matters on this institution." emptyAction={<ButtonLink to="/cases/new" variant="tertiary">New case</ButtonLink>} />
            <DataTable columns={cols.slice(0, 3)} rows={[]} rowKey={(r) => r.id} errorMessage="The case register could not be loaded." />
          </div>
        </Section>

        <Section title="Tabs, fields">
          <Tabs value={tab} onChange={setTab} tabs={[{ id: 'summary', label: 'Summary' }, { id: 'passport', label: 'Case Passport' }, { id: 'links', label: 'Linked cases', count: 2 }, { id: 'src', label: 'Source records' }]} />
          <div className="mt-4 grid grid-cols-4 gap-4">
            <Field label="Institution as written" required hint="Free text; Hindi is accepted."><Input placeholder="e.g. Shrinath Engg College Kanpur" /></Field>
            <Field label="Permanent ID" hint="Optional"><Input mono placeholder="1-4463974255" /></Field>
            <Field label="Channel"><Select defaultValue="CSS"><option value="CSS">CSS</option><option value="EMAIL">Email</option></Select></Field>
            <Field label="Subject" error="Subject is required."><Input defaultValue="" aria-invalid /></Field>
            <Field label="Description" className="col-span-2"><Textarea defaultValue="फीस वापस नहीं कर रहे" /></Field>
            <div className="flex flex-col gap-1">
              <Checkbox label="I have seen the 5 open matters listed above." />
              <Checkbox label="Disabled option" disabled />
            </div>
            <Field label="Disabled"><Input disabled value="Read only" readOnly /></Field>
          </div>
        </Section>

        <Section title="PassportTimeline (unverified / verified / broken)">
          <div className="grid grid-cols-3 gap-4">
            <Panel title="Not yet verified"><PassportTimeline entries={ENTRIES} onVerify={() => setVerification({ ok: true, count: ENTRIES.length, checked_at: new Date().toISOString() })} /></Panel>
            <Panel title="Verified"><PassportTimeline entries={ENTRIES} verification={verification ?? { ok: true, count: ENTRIES.length, checked_at: '2026-11-01T09:50:00Z' }} /></Panel>
            <Panel title="Broken chain"><PassportTimeline entries={ENTRIES} verification={{ ok: false, count: ENTRIES.length, first_bad_seq: 3, checked_at: '2026-11-01T09:50:00Z' }} /></Panel>
          </div>
        </Section>

        <Section title="Overlays, menus, toast, skeleton, cold start, chart">
          <Row>
            <Button onClick={() => setDrawer(true)}>Open drawer</Button>
            <Button onClick={() => setModal(true)}>Open modal</Button>
            <Button onClick={() => toast('Link confirmed. Passport entry a3f9…c21e written.', 'ok')}>Toast: ok</Button>
            <Button onClick={() => toast('Could not reach the server.', 'red')}>Toast: error</Button>
            <DropdownMenu
              items={[
                { key: 'noc', label: 'Issue NOC' },
                { key: 'dep', label: 'Security-deposit release' },
                { key: 'sc', label: 'Show-cause' },
                { key: 'x', label: 'Closure approval', separator: true },
              ]}
              trigger={({ toggle, open }) => <Button aria-haspopup="menu" aria-expanded={open} onClick={toggle}>Actions</Button>}
            />
          </Row>
          <div className="mt-3 grid grid-cols-2 gap-4">
            <Panel title="Skeletons"><div className="flex flex-col gap-2"><Skeleton width={180} height={20} /><Skeleton /><Skeleton width="70%" /></div><SkeletonRows rows={3} cols={4} /></Panel>
            <Panel title="Open cases by bureau and status" actions={<Button variant="tertiary">View cases</Button>} bodyClassName="p-2">
              <ReactECharts theme={theme} option={chart} style={{ height: 220 }} notMerge />
            </Panel>
          </div>
          <div className="mt-3 border border-line"><ColdStartBanner forceVisible /></div>
          <div className="mt-3"><EmptyState message="No open matters on this institution." action={<Button variant="tertiary">Register a case</Button>} /></div>
        </Section>
      </div>

      <Drawer open={drawer} onClose={() => setDrawer(false)} title="LS-2026-000204" subtitle="Fee refund · Shrinath Institute of Engineering & Technology" footer={<><Button onClick={() => setDrawer(false)}>Close</Button><Button variant="primary">Open case</Button></>}>
        <div className="flex flex-col gap-3">
          <Row><StatusTag status="AWAITING_ATR" /><ClockPill label="Inst. 7-day · overdue 4d" state="BREACHED" clause="APH 2024-27 cl. 6.45" /><RelationBadge relation="RELATED" /></Row>
          <ReasonList reasons={REASONS.slice(0, 3)} />
        </div>
      </Drawer>
      <Modal open={modal} onClose={() => setModal(false)} title="Reason for revealing complainant details" footer={<><Button onClick={() => setModal(false)}>Cancel</Button><Button variant="primary" onClick={() => setModal(false)}>Reveal</Button></>}>
        <Field label="Reason (minimum 10 characters)" required><Textarea rows={3} /></Field>
      </Modal>
    </div>
  );
}
