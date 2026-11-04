import { useEffect, useMemo, useState } from 'react';
import { Button, EmptyState, Panel, Skeleton, useToast } from '@/components/ui';
import { errorMessage } from '@/api/client';
import { formatDateTime } from '@/lib/format';
import { useConfig, usePutConfig } from './adminApi';

const LABELS: Record<string, { label: string; hint: string }> = {
  inst_auto: { label: 'Institution match: auto-suggest', hint: 'At or above this score the institution is pre-selected; the officer can still change it.' },
  inst_review: { label: 'Institution match: review', hint: 'Between this score and auto-suggest the officer must confirm. Below it the match is unresolved.' },
  dup: { label: 'Duplicate link', hint: 'At or above this score two cases are suggested as "Review suggested".' },
  related: { label: 'Related link', hint: 'At or above this score two cases are suggested as "Coordination required".' },
};
const ORDER = ['inst_auto', 'inst_review', 'dup', 'related'];

type Values = Record<string, number>;

export function ThresholdsTab() {
  const cfg = useConfig<Values>('thresholds');
  const put = usePutConfig<Values>('thresholds');
  const { toast } = useToast();
  const [draft, setDraft] = useState<Values>({});
  const saved = cfg.data?.value;

  useEffect(() => {
    if (saved) setDraft(saved);
  }, [saved]);

  const keys = useMemo(() => {
    const present = Object.keys(saved ?? {});
    return [...ORDER.filter((k) => present.includes(k)), ...present.filter((k) => !ORDER.includes(k))];
  }, [saved]);

  const dirty = !!saved && keys.some((k) => draft[k] !== saved[k]);
  const errors: string[] = [];
  if (draft.inst_review !== undefined && draft.inst_auto !== undefined && !(draft.inst_review < draft.inst_auto)) errors.push('The review threshold must be lower than the auto-suggest threshold.');
  if (draft.related !== undefined && draft.dup !== undefined && !(draft.related < draft.dup)) errors.push('The related threshold must be lower than the duplicate threshold.');

  const save = () => {
    const changed: Values = {};
    keys.forEach((k) => {
      if (draft[k] !== saved?.[k]) changed[k] = draft[k];
    });
    put.mutate(changed, {
      onSuccess: () => toast('Thresholds saved.', 'ok'),
      onError: (e) => toast(`Could not save thresholds. ${errorMessage(e)}`, 'red'),
    });
  };

  return (
    <Panel
      title="Matching thresholds"
      actions={cfg.data?.updated_at ? <span className="text-xs text-ink-500">Last changed {formatDateTime(cfg.data.updated_at)}</span> : undefined}
    >
      <p className="mb-4 max-w-[720px] text-sm text-ink-700">Starting values; tune on labelled data. Changes apply to new matches and the next relationship sweep. They never merge, block or cancel anything.</p>
      {cfg.isLoading && <Skeleton height={160} />}
      {cfg.error && <EmptyState tone="error" message={`Could not load thresholds. ${cfg.error.message}`} />}
      {saved && (
        <div className="flex max-w-[720px] flex-col gap-4">
          {keys.map((k) => {
            const meta = LABELS[k] ?? { label: k, hint: '' };
            const v = draft[k] ?? 0;
            return (
              <div key={k} className="grid grid-cols-[minmax(0,1fr)_240px_88px] items-center gap-4">
                <div>
                  <label htmlFor={`th-${k}`} className="text-sm font-medium text-ink-900">
                    {meta.label}
                  </label>
                  <div className="text-xs text-ink-500">{meta.hint}</div>
                </div>
                <input
                  type="range"
                  aria-label={`${meta.label} slider`}
                  min={0}
                  max={1}
                  step={0.01}
                  value={v}
                  onChange={(e) => setDraft((d) => ({ ...d, [k]: Number(e.target.value) }))}
                  className="focus-ring w-full accent-navy"
                />
                <input
                  id={`th-${k}`}
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={v}
                  onChange={(e) => setDraft((d) => ({ ...d, [k]: Number(e.target.value) }))}
                  className="focus-ring h-ctl w-full rounded border border-line bg-surface px-2.5 text-right font-mono text-sm tnum hover:border-ink-300"
                />
              </div>
            );
          })}
          {errors.map((e) => (
            <p key={e} className="text-sm text-red">
              {e}
            </p>
          ))}
          <div className="flex gap-2">
            <Button variant="primary" disabled={!dirty || errors.length > 0} loading={put.isPending} onClick={save}>
              Save thresholds
            </Button>
            <Button disabled={!dirty} onClick={() => setDraft(saved)}>
              Discard changes
            </Button>
          </div>
        </div>
      )}
    </Panel>
  );
}
