import { useEffect, useState } from 'react';
import { Button, EmptyState, Panel, Select, Skeleton, useToast } from '@/components/ui';
import { errorMessage } from '@/api/client';
import { BUREAUS, BUREAU_FULL_NAME, CATEGORY_LABEL, type Bureau, type CaseCategory } from '@/lib/constants';
import { useConfig, usePutConfig } from './adminApi';

type Rules = Record<string, string>;

/** Lead bureau suggestion per complaint category. Suggestions only; officers can change them on a link. */
export function LeadRulesTab() {
  const cfg = useConfig<Rules>('lead_bureau_rules');
  const put = usePutConfig<Rules>('lead_bureau_rules');
  const { toast } = useToast();
  const [draft, setDraft] = useState<Rules>({});
  useEffect(() => {
    if (cfg.data) setDraft(cfg.data.value ?? {});
  }, [cfg.data]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(cfg.data?.value ?? {});

  const save = () => {
    const clean: Rules = {};
    Object.entries(draft).forEach(([k, v]) => {
      if (v) clean[k] = v;
    });
    put.mutate(clean, {
      onSuccess: () => toast('Lead bureau rules saved.', 'ok'),
      onError: (e) => toast(`Could not save. ${errorMessage(e)}`, 'red'),
    });
  };

  return (
    <Panel title="Lead bureau suggestion by category" padded={false}>
      <p className="px-3 pt-3 text-sm text-ink-700">
        When two bureaus act on the same institution, the link compare screen suggests the bureau below as lead. This is a suggestion; the officers decide.
      </p>
      {cfg.isLoading && <div className="p-3"><Skeleton height={160} /></div>}
      {cfg.error && <EmptyState tone="error" message={`Could not load lead bureau rules. ${cfg.error.message}`} />}
      {cfg.data && (
        <>
          <table className="ls-table mt-3">
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col" style={{ width: 260 }}>
                  Suggested lead bureau
                </th>
              </tr>
            </thead>
            <tbody>
              {(Object.keys(CATEGORY_LABEL) as CaseCategory[]).map((c) => (
                <tr key={c}>
                  <td>{CATEGORY_LABEL[c]}</td>
                  <td style={{ padding: '4px 12px' }}>
                    <Select aria-label={`Lead bureau for ${CATEGORY_LABEL[c]}`} value={draft[c] ?? ''} onChange={(e) => setDraft((d) => ({ ...d, [c]: e.target.value }))}>
                      <option value="">No suggestion</option>
                      {BUREAUS.filter((b) => b !== 'ADMIN').map((b) => (
                        <option key={b} value={b}>
                          {BUREAU_FULL_NAME[b as Bureau]}
                        </option>
                      ))}
                    </Select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex gap-2 border-t border-line p-3">
            <Button variant="primary" disabled={!dirty} loading={put.isPending} onClick={save}>
              Save rules
            </Button>
            <Button disabled={!dirty} onClick={() => setDraft(cfg.data?.value ?? {})}>
              Discard changes
            </Button>
          </div>
        </>
      )}
    </Panel>
  );
}
