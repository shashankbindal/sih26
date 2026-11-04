import { useEffect, useState } from 'react';
import { Button, EmptyState, Field, Input, Panel, Skeleton, useToast } from '@/components/ui';
import { api, errorMessage } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { formatNumber } from '@/lib/format';
import { useConfig } from './adminApi';

interface ClockCfg {
  duration_hours: number;
  short_label: string;
  long_label?: string | null;
  rule?: string | null;
  clause_key?: string | null;
}
type Clocks = Record<string, ClockCfg>;
type Clauses = Record<string, string>;

const CLOCK_ORDER = ['CPGRAMS_21D', 'CSS_72H', 'INST_REFUND_7D'];
const CLAUSE_NAME: Record<string, string> = { refund: 'Fee refund and certificate return', deposit: 'Security-deposit release' };

function duration(hours: number): string {
  if (!Number.isFinite(hours)) return '';
  return hours % 24 === 0 ? `${formatNumber(hours / 24)} days` : `${formatNumber(hours)} hours`;
}

export function ClocksTab() {
  const clocksQ = useConfig<Clocks>('clocks');
  const clausesQ = useConfig<Clauses>('clause_labels');
  const amberQ = useConfig<number>('amber_ratio');
  const { toast } = useToast();
  const [clocks, setClocks] = useState<Clocks>({});
  const [clauses, setClauses] = useState<Clauses>({});
  const [amber, setAmber] = useState(0);

  useEffect(() => {
    if (clocksQ.data) setClocks(clocksQ.data.value);
  }, [clocksQ.data]);
  useEffect(() => {
    if (clausesQ.data) setClauses(clausesQ.data.value);
  }, [clausesQ.data]);
  useEffect(() => {
    if (amberQ.data) setAmber(amberQ.data.value);
  }, [amberQ.data]);

  const save = useApiMutation(
    async () => {
      const changedClocks: Record<string, Partial<ClockCfg>> = {};
      for (const [k, cfg] of Object.entries(clocks)) {
        const base = clocksQ.data?.value[k];
        if (!base) continue;
        const diff: Partial<ClockCfg> = {};
        if (cfg.duration_hours !== base.duration_hours) diff.duration_hours = cfg.duration_hours;
        if (cfg.short_label !== base.short_label) diff.short_label = cfg.short_label;
        if ((cfg.long_label ?? '') !== (base.long_label ?? '')) diff.long_label = cfg.long_label ?? '';
        if (Object.keys(diff).length) changedClocks[k] = diff;
      }
      const changedClauses: Clauses = {};
      for (const [k, v] of Object.entries(clauses)) if (v !== clausesQ.data?.value[k]) changedClauses[k] = v;
      if (Object.keys(changedClocks).length) await api.put('/admin/config/clocks', { value: changedClocks });
      if (Object.keys(changedClauses).length) await api.put('/admin/config/clause_labels', { value: changedClauses });
      if (amber !== amberQ.data?.value) await api.put('/admin/config/amber_ratio', { value: amber });
    },
    {
      invalidate: [['admin', 'config'], ['policy'], ['dash']],
      onSuccess: () => toast('Policy clock settings saved.', 'ok'),
      onError: (e) => toast(`Could not save. ${errorMessage(e)}`, 'red'),
    },
  );

  const loading = clocksQ.isLoading || clausesQ.isLoading || amberQ.isLoading;
  const error = clocksQ.error ?? clausesQ.error ?? amberQ.error;
  const dirty =
    JSON.stringify(clocks) !== JSON.stringify(clocksQ.data?.value ?? {}) ||
    JSON.stringify(clauses) !== JSON.stringify(clausesQ.data?.value ?? {}) ||
    amber !== (amberQ.data?.value ?? amber);
  const keys = [...CLOCK_ORDER.filter((k) => clocks[k]), ...Object.keys(clocks).filter((k) => !CLOCK_ORDER.includes(k))];

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-[760px] text-sm text-ink-700">
        Three separate clocks, each from a different rule. They are never combined into one measure. Durations are counted from the start point described in the rule.
      </p>
      {loading && <Skeleton height={200} />}
      {error && <EmptyState tone="error" message={`Could not load clock settings. ${error.message}`} />}
      {!loading && !error && (
        <>
          <Panel title="Clock durations and labels" padded={false}>
            <table className="ls-table">
              <thead>
                <tr>
                  <th scope="col">Clock</th>
                  <th scope="col" style={{ width: 190 }}>
                    Duration (hours)
                  </th>
                  <th scope="col" style={{ width: 150 }}>
                    Short label
                  </th>
                  <th scope="col" style={{ width: 260 }}>Full label</th>
                  <th scope="col">Rule shown in tooltips</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => {
                  const c = clocks[k];
                  const rule = c.clause_key ? clauses[c.clause_key] : c.rule;
                  return (
                    <tr key={k}>
                      <td className="id" style={{ height: 52 }}>
                        {k}
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <Input
                            mono
                            type="number"
                            min={1}
                            max={8760}
                            aria-label={`${k} duration in hours`}
                            className="!w-20 text-right"
                            value={c.duration_hours}
                            onChange={(e) => setClocks((cur) => ({ ...cur, [k]: { ...cur[k], duration_hours: Number(e.target.value) } }))}
                          />
                          <span className="tnum whitespace-nowrap text-xs text-ink-500">{duration(c.duration_hours)}</span>
                        </div>
                      </td>
                      <td>
                        <Input aria-label={`${k} short label`} value={c.short_label} onChange={(e) => setClocks((cur) => ({ ...cur, [k]: { ...cur[k], short_label: e.target.value } }))} />
                      </td>
                      <td>
                        <Input aria-label={`${k} full label`} value={c.long_label ?? ''} onChange={(e) => setClocks((cur) => ({ ...cur, [k]: { ...cur[k], long_label: e.target.value } }))} />
                      </td>
                      <td className="text-xs text-ink-500">{rule || '–'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Panel>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Clause labels">
              <div className="flex flex-col gap-3">
                {Object.keys(clauses).map((k) => (
                  <Field key={k} label={CLAUSE_NAME[k] ?? k} hint={`Key: ${k}`}>
                    <Input value={clauses[k]} onChange={(e) => setClauses((cur) => ({ ...cur, [k]: e.target.value }))} />
                  </Field>
                ))}
              </div>
            </Panel>
            <Panel title="Amber ratio">
              <p className="mb-3 text-sm text-ink-700">A clock turns amber (&quot;Due soon&quot;) once this share of its duration has elapsed.</p>
              <div className="flex items-center gap-4">
                <input type="range" aria-label="Amber ratio slider" min={0.1} max={0.99} step={0.01} value={amber} onChange={(e) => setAmber(Number(e.target.value))} className="focus-ring w-56 accent-navy" />
                <Input mono type="number" min={0.1} max={0.99} step={0.01} aria-label="Amber ratio" className="!w-24 text-right" value={amber} onChange={(e) => setAmber(Number(e.target.value))} />
                <span className="tnum whitespace-nowrap text-sm text-ink-500">{formatNumber(amber * 100)}% elapsed</span>
              </div>
            </Panel>
          </div>
          <div>
            <Button variant="primary" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate(undefined)}>
              Save clock settings
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
