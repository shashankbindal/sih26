import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import {
  BarChart3,
  ClipboardCheck,
  FilePlus2,
  FolderOpen,
  Gauge,
  GitCompareArrows,
  Landmark,
  Search as SearchIcon,
  Settings,
  Upload,
  FlaskConical,
  Info,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '@/auth';
import { useCount } from '@/api/hooks';
import { cx } from '@/lib/cx';
import { ICON } from '@/lib/icons';
import type { Role } from '@/lib/constants';
import { Wordmark } from './Wordmark';

interface Item {
  to: string;
  label: string;
  hi?: string;
  icon: LucideIcon;
  end?: boolean;
  roles?: Role[];
  count?: number;
  coordination?: boolean;
}

const WORK: Role[] = ['PGRC_OFFICER', 'RB_OFFICER', 'APPROVAL_OFFICER', 'VIGILANCE_OFFICER', 'RO_OFFICER', 'BUREAU_HEAD', 'ADMIN'];

function Count({ n, coordination }: { n?: number; coordination?: boolean }) {
  if (!n) return null;
  return (
    <span
      className={cx(
        'ml-auto inline-flex h-4 min-w-[18px] items-center justify-center rounded-sm px-1 font-mono text-2xs font-medium tnum',
        coordination ? 'bg-saffron text-ink-900' : 'bg-ink-700 text-surface',
      )}
      aria-label={`${n} pending`}
    >
      {n}
    </span>
  );
}

function NavItem({ item }: { item: Item }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        cx(
          'focus-ring mx-2 flex items-center gap-2.5 rounded px-2.5 text-sm text-surface hover:bg-ink-700 hover:no-underline',
          item.hi ? 'min-h-[42px] py-1' : 'h-8',
          isActive && '!bg-navy',
        )
      }
    >
      <item.icon {...ICON} className="shrink-0 opacity-80" />
      <span className="min-w-0 leading-tight">
        <span className="block">{item.label}</span>
        {item.hi && (
          <span lang="hi" className="block text-2xs text-on-dark">
            {item.hi}
          </span>
        )}
      </span>
      <Count n={item.count} coordination={item.coordination} />
    </NavLink>
  );
}

function Group({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="mt-3 first:mt-0">
      {label && <div className="px-4 pb-1 pt-1 text-2xs font-semibold uppercase tracking-[0.04em] text-on-dark">{label}</div>}
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  );
}

export function SideNav() {
  const { user } = useAuth();
  const isWork = !!user && WORK.includes(user.role);
  // Badges use the same definitions as the default inbox tabs ("Needs my decision", "Pending") so numbers always agree.
  const coordination = useCount('links-needs', '/links', { needs_my_decision: true }, isWork);
  const clearances = useCount('clearances-pending', '/clearances', { inbox: 'me', status: ['PENDING'] }, isWork);
  const review = useCount('review', '/review/institution-matches', {}, isWork);

  const main: Item[] = [
    { to: '/', label: 'Dashboard', hi: 'डैशबोर्ड', icon: Gauge, end: true },
    { to: '/cases', label: 'Cases', hi: 'मामले', icon: FolderOpen, end: true },
    { to: '/institutions', label: 'Institutions', hi: 'संस्थान', icon: Landmark },
  ];
  const coord: Item[] = [
    { to: '/coordination', label: 'Coordination', hi: 'समन्वय', icon: GitCompareArrows, count: coordination, coordination: true, roles: WORK },
    { to: '/clearances', label: 'Clearances', icon: ClipboardCheck, count: clearances, roles: WORK },
    { to: '/review', label: 'Review queue', icon: SearchIcon, count: review, roles: WORK },
  ];
  const work: Item[] = [
    { to: '/cases/new', label: 'New case', icon: FilePlus2, roles: WORK },
    { to: '/import', label: 'Import', icon: Upload, roles: WORK },
  ];
  const insight: Item[] = [
    { to: '/reports', label: 'Reports', icon: BarChart3 },
    { to: '/evaluation', label: 'Evaluation', icon: FlaskConical },
  ];
  const admin: Item[] = [{ to: '/admin', label: 'Admin', icon: Settings, roles: ['ADMIN'] }];

  const visible = (items: Item[]) => items.filter((i) => !i.roles || (user && i.roles.includes(user.role)));

  return (
    <nav aria-label="Main" className="flex w-nav shrink-0 flex-col overflow-y-auto bg-ink-900 text-surface">
      <div className="flex h-topbar shrink-0 items-center border-b border-ink-700 px-4">
        <Wordmark />
      </div>
      <div className="flex-1 py-3">
        <Group>{visible(main).map((i) => <NavItem key={i.to} item={i} />)}</Group>
        {visible(coord).length > 0 && <Group label="Coordination">{visible(coord).map((i) => <NavItem key={i.to} item={i} />)}</Group>}
        {visible(work).length > 0 && <Group label="Work">{visible(work).map((i) => <NavItem key={i.to} item={i} />)}</Group>}
        <Group label="Insight">{visible(insight).map((i) => <NavItem key={i.to} item={i} />)}</Group>
        {visible(admin).length > 0 && <Group label="System">{visible(admin).map((i) => <NavItem key={i.to} item={i} />)}</Group>}
      </div>
      <div className="shrink-0 border-t border-ink-700 py-2">
        <NavItem item={{ to: '/home', label: 'How it works', icon: Info }} />
      </div>
    </nav>
  );
}
