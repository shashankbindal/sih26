import { useSearchParams } from 'react-router-dom';
import { Tabs } from '@/components/ui';
import { ClocksTab } from './ClocksTab';
import { DemoToolsTab } from './DemoToolsTab';
import { LeadRulesTab } from './LeadRulesTab';
import { ThresholdsTab } from './ThresholdsTab';
import { UsersTab } from './UsersTab';

const TABS = [
  { id: 'thresholds', label: 'Thresholds' },
  { id: 'clocks', label: 'Policy clocks' },
  { id: 'lead', label: 'Lead bureau rules' },
  { id: 'users', label: 'Users' },
  { id: 'demo', label: 'Demo tools' },
];

export default function AdminPage() {
  const [sp, setSp] = useSearchParams();
  const raw = sp.get('tab');
  const tab = TABS.some((t) => t.id === raw) ? (raw as string) : 'thresholds';
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-ink-900">Administration</h1>
      <Tabs ariaLabel="Administration sections" tabs={TABS} value={tab} onChange={(id) => setSp({ tab: id }, { replace: true })} />
      <div role="tabpanel">
        {tab === 'thresholds' && <ThresholdsTab />}
        {tab === 'clocks' && <ClocksTab />}
        {tab === 'lead' && <LeadRulesTab />}
        {tab === 'users' && <UsersTab />}
        {tab === 'demo' && <DemoToolsTab />}
      </div>
    </div>
  );
}
