import { useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { RotateCw } from 'lucide-react';
import { Badge, Button, DataTable, EmptyState, Panel, Skeleton, useToast, type Column } from '@/components/ui';
import { api, errorMessage } from '@/api/client';
import { useApiMutation, useApiQuery } from '@/api/hooks';
import { formatDateTime, formatNumber } from '@/lib/format';

// Shape follows backend/app/services/evaluation.py (compute()). Nothing is computed or invented here:
// every figure is shown with the N it was measured on.
interface Band {
  band: string;
  n_in_band: number;
  correct: number;
  n_total: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
}
interface Hits {
  value: number | null;
  hits: number;
  n: number;
  review_top_k?: number;
}
interface StageA {
  n: number;
  n_unlabelled_excluded?: number;
  bands: Band[];
  needs_review_true_in_top3: Hits;
  unresolved: { n: number; true_in_candidates: number };
  recall_at_auto_review: Hits;
  top1_accuracy: Hits;
  wrong_auto: { n: number; of: number };
}
interface ClassRow {
  relation: string;
  n_true: number;
  n_predicted: number;
  true_positives: number;
  precision: number | null;
  recall: number | null;
}
interface StageB {
  n_pairs: number;
  n_cases: number;
  labels: string[];
  confusion_matrix: number[][];
  classes: ClassRow[];
  alert_precision: { value: number | null; true_alerts: number; alerts: number; strict_value: number | null };
}
interface Target {
  name: string;
  target: number;
  measured: number | null;
  n: number;
  passed: boolean | null;
  text: string;
}
interface Failure {
  stage: 'A' | 'B';
  kind: string;
  case: string;
  other_case: string | null;
  institution: string;
  expected: string | null;
  predicted: string | null;
  score: number;
  reasons: string[];
}
interface Evaluation {
  split: string;
  split_source: string;
  evaluated_institutions: number;
  generated_at: string | number;
  duration_ms: number;
  cached: boolean;
  thresholds_used: Record<string, number>;
  stage_a: StageA;
  stage_b: StageB;
  targets: Target[];
  failure_cases: Failure[];
  failure_total: number;
  notes: string[];
}

const pct = (v: number | null | undefined) => (v === null || v === undefined ? '–' : `${(v * 100).toFixed(1)}%`);
const ratio = (v: number | null, hits: number, n: number) => (v === null ? `no cases (N=${formatNumber(n)})` : `${pct(v)} (${formatNumber(hits)} of ${formatNumber(n)})`);

const BAND_LABEL: Record<string, string> = {
  EXACT: 'Exact (Permanent ID or alias)',
  AUTO_SUGGESTED: 'Auto-suggested',
  'AUTO (EXACT + AUTO_SUGGESTED)': 'Auto band (exact and auto-suggested)',
  'NEEDS_REVIEW (top-1)': 'Needs review (top candidate)',
};
const THRESHOLD_LABEL: Record<string, string> = {
  inst_auto: 'Institution auto-suggest',
  inst_review: 'Institution review',
  near_twin_gap: 'Near-twin gap (forces review)',
  dup: 'Duplicate link',
  dup_strict: 'Duplicate link (strict)',
  related: 'Related link',
  conflict_overlap: 'Conflict overlap',
};
const REL_LABEL: Record<string, string> = { UNRELATED: 'Unrelated', DUPLICATE: 'Duplicate', RELATED: 'Related', CONFLICTING: 'Conflicting' };

function kindLabel(k: string): string {
  const fixed: Record<string, string> = {
    WRONG_AUTO_MATCH: 'Wrong institution auto-suggested',
    TRUE_INSTITUTION_NOT_SHOWN: 'Correct institution not among the candidates',
    NO_CONFIDENT_MATCH: 'No confident institution match',
    FALSE_ALERT: 'Alert raised on an unrelated pair',
  };
  if (fixed[k]) return fixed[k];
  const missed = /^MISSED_(\w+)$/.exec(k);
  if (missed) return `Missed ${REL_LABEL[missed[1]]?.toLowerCase() ?? missed[1].toLowerCase()} pair`;
  const wrong = /^WRONG_RELATION_(\w+?)_AS_(\w+)$/.exec(k);
  if (wrong) return `${REL_LABEL[wrong[1]] ?? wrong[1]} pair classed as ${REL_LABEL[wrong[2]]?.toLowerCase() ?? wrong[2].toLowerCase()}`;
  return k;
}

/** Five discrete navy steps (single hue, no gradient). Share is the cell's share of its row. */
function shade(share: number): { bg: string; fg: string } {
  if (share <= 0) return { bg: 'transparent', fg: 'var(--ink-500)' };
  if (share < 0.1) return { bg: 'rgba(18, 50, 94, 0.08)', fg: 'var(--ink-900)' };
  if (share < 0.3) return { bg: 'rgba(18, 50, 94, 0.2)', fg: 'var(--ink-900)' };
  if (share < 0.6) return { bg: 'rgba(18, 50, 94, 0.45)', fg: '#ffffff' };
  return { bg: 'rgba(18, 50, 94, 0.85)', fg: '#ffffff' };
}

function ConfusionMatrix({ b }: { b: StageB }) {
  const rowTotals = b.confusion_matrix.map((r) => r.reduce((a, x) => a + x, 0));
  const colTotals = b.labels.map((_l, c) => b.confusion_matrix.reduce((a, r) => a + r[c], 0));
  return (
    <div>
      <table className="w-full border-collapse text-sm" aria-label="Relationship confusion matrix">
        <caption className="sr-only">Rows are the true relation, columns are the predicted relation. Cell shade is the share of the row.</caption>
        <thead>
          <tr>
            <th scope="col" className="p-2 text-left text-xs font-semibold text-ink-500">
              True relation
            </th>
            {b.labels.map((l) => (
              <th key={l} scope="col" className="p-2 text-right text-xs font-semibold text-ink-500">
                Predicted {REL_LABEL[l]?.toLowerCase() ?? l}
              </th>
            ))}
            <th scope="col" className="p-2 text-right text-xs font-semibold text-ink-500">
              N true
            </th>
          </tr>
        </thead>
        <tbody>
          {b.labels.map((l, r) => (
            <tr key={l}>
              <th scope="row" className="p-2 text-left font-medium text-ink-900">
                {REL_LABEL[l] ?? l}
              </th>
              {b.confusion_matrix[r].map((v, c) => {
                const s = shade(rowTotals[r] ? v / rowTotals[r] : 0);
                return (
                  <td key={c} className="tnum border border-surface p-2 text-right" style={{ background: s.bg, color: s.fg, fontWeight: r === c ? 600 : 400, minWidth: 92 }}>
                    {formatNumber(v)}
                  </td>
                );
              })}
              <td className="tnum p-2 text-right text-ink-700">{formatNumber(rowTotals[r])}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" className="p-2 text-left text-xs font-semibold text-ink-500">
              N predicted
            </th>
            {colTotals.map((t, i) => (
              <td key={i} className="tnum p-2 text-right text-ink-700">
                {formatNumber(t)}
              </td>
            ))}
            <td className="tnum p-2 text-right font-medium text-ink-900">{formatNumber(b.n_pairs)}</td>
          </tr>
        </tfoot>
      </table>
      <p className="mt-2 text-xs text-ink-500">
        Rows: true relation from the seed labels. Columns: relation predicted by CaseLink. Darker cells hold a larger share of their row. N is the number of case pairs on the same institution.
      </p>
    </div>
  );
}

export default function EvaluationPage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const q = useApiQuery<Evaluation>(['evaluation'], '/evaluation/run', { params: { split: 'heldout' }, staleTime: 5 * 60_000 });
  const rerun = useApiMutation(() => api.get<Evaluation>('/evaluation/run', { params: { split: 'heldout', refresh: true } }), {
    onSuccess: (data) => {
      qc.setQueryData(['evaluation', { split: 'heldout' }], data);
      toast('Evaluation re-run on the held-out set.', 'ok');
    },
    onError: (e) => toast(`Could not re-run the evaluation. ${errorMessage(e)}`, 'red'),
  });
  const ev = q.data;

  const bandCols: Column<Band>[] = [
    { key: 'band', header: 'Band', render: (b) => BAND_LABEL[b.band] ?? b.band },
    { key: 'n', header: 'N in band', numeric: true, render: (b) => formatNumber(b.n_in_band) },
    { key: 'p', header: 'Precision', numeric: true, render: (b) => ratio(b.precision, b.correct, b.n_in_band) },
    { key: 'r', header: 'Recall', numeric: true, render: (b) => ratio(b.recall, b.correct, b.n_total) },
    { key: 'f1', header: 'F1', numeric: true, render: (b) => (b.f1 === null ? '–' : b.f1.toFixed(2)) },
  ];
  const classCols: Column<ClassRow>[] = [
    { key: 'rel', header: 'Relation', render: (c) => REL_LABEL[c.relation] ?? c.relation },
    { key: 'nt', header: 'N true', numeric: true, render: (c) => formatNumber(c.n_true) },
    { key: 'np', header: 'N predicted', numeric: true, render: (c) => formatNumber(c.n_predicted) },
    { key: 'p', header: 'Precision', numeric: true, render: (c) => ratio(c.precision, c.true_positives, c.n_predicted) },
    { key: 'r', header: 'Recall', numeric: true, render: (c) => ratio(c.recall, c.true_positives, c.n_true) },
  ];
  const failCols: Column<Failure & { __k: string }>[] = useMemo(
    () => [
      {
        key: 'kind',
        header: 'What went wrong',
        width: 230,
        render: (f) => (
          <div className="py-1.5">
            <div className="font-medium text-ink-900">{kindLabel(f.kind)}</div>
            <div className="text-xs text-ink-500">{f.stage === 'A' ? 'Institution match' : 'Relationship'}</div>
          </div>
        ),
      },
      {
        key: 'case',
        header: 'Case and institution',
        width: 250,
        render: (f) => (
          <div className="py-1.5">
            <div className="mono text-xs">
              {f.case}
              {f.other_case ? ` / ${f.other_case}` : ''}
            </div>
            <div className="max-w-[230px] truncate text-xs text-ink-500" title={f.institution}>
              {f.institution}
            </div>
          </div>
        ),
      },
      {
        key: 'exp',
        header: 'Expected, predicted, score',
        width: 210,
        render: (f) => (
          <div className="py-1.5 text-xs">
            <div>
              Expected: {REL_LABEL[f.expected ?? ''] ?? f.expected ?? 'none'}
            </div>
            <div>
              Predicted: {REL_LABEL[f.predicted ?? ''] ?? f.predicted ?? 'none'} <span className="mono text-ink-500">({f.score.toFixed(2)})</span>
            </div>
          </div>
        ),
      },
      {
        key: 'reasons',
        header: 'Likely reasons',
        render: (f) => (
          <ul className="list-disc py-1.5 pl-4 text-xs text-ink-700">
            {f.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        ),
      },
    ],
    [],
  );
  const failRows = useMemo(() => (ev?.failure_cases ?? []).map((f, i) => ({ ...f, __k: String(i) })), [ev?.failure_cases]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink-900">Matching evaluation</h1>
          <p className="mt-1 text-sm text-ink-700">How well does CaseLink match? Measured on a held-out synthetic set.</p>
          {ev && (
            <p className="mt-0.5 text-xs text-ink-500 tnum">
              Held-out institutions: {formatNumber(ev.evaluated_institutions)}. Split: {ev.split_source}. Run {typeof ev.generated_at === 'string' ? formatDateTime(ev.generated_at) : ev.cached ? 'earlier' : 'now'} in {formatNumber(ev.duration_ms)} ms{ev.cached ? ' (cached result)' : ''}.
            </p>
          )}
        </div>
        <Button icon={RotateCw} loading={rerun.isPending} onClick={() => rerun.mutate(undefined)}>
          Re-run
        </Button>
      </div>

      {q.isLoading && (
        <div role="status" aria-label="Running evaluation" className="flex flex-col gap-3">
          <Skeleton height={120} />
          <Skeleton height={200} />
          <p className="text-sm text-ink-500">Running the matcher on the held-out set. This can take a few seconds.</p>
        </div>
      )}
      {q.error && (
        <Panel>
          <EmptyState tone="error" message={`The evaluation could not be loaded. ${q.error.message}`} action={<Button onClick={() => void q.refetch()}>Retry</Button>} />
        </Panel>
      )}

      {ev && (
        <>
          <Panel title="Pilot targets and what was measured" padded={false}>
            <ul className="divide-y divide-line-soft">
              {ev.targets.map((t) => (
                <li key={t.name} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2.5">
                  <div>
                    <div className="text-sm font-medium text-ink-900">{t.name}</div>
                    <div className="text-xs text-ink-500 tnum">{t.text}</div>
                  </div>
                  <Badge tone={t.passed === null ? 'neutral' : t.passed ? 'ok' : 'red'}>{t.passed === null ? 'Not measured' : t.passed ? 'Pass' : 'Not met'}</Badge>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="Institution matching (stage A)" padded={false}>
            <p className="px-3 py-2 text-sm text-ink-700">
              Each labelled complaint is matched against the full register. N = <span className="tnum font-medium">{formatNumber(ev.stage_a.n)}</span> labelled complaints
              {ev.stage_a.n_unlabelled_excluded ? `; ${formatNumber(ev.stage_a.n_unlabelled_excluded)} without a label excluded` : ''}. Precision is computed within a band, recall over all N.
            </p>
            <DataTable compact caption="Institution matching by band" columns={bandCols} rows={ev.stage_a.bands} rowKey={(b) => b.band} className="rounded-none border-x-0" />
            <dl className="grid grid-cols-1 gap-x-8 gap-y-1 px-3 py-3 text-sm md:grid-cols-2">
              <div className="flex justify-between gap-3">
                <dt className="text-ink-500">Recall, auto and review bands</dt>
                <dd className="tnum text-right">{ratio(ev.stage_a.recall_at_auto_review.value, ev.stage_a.recall_at_auto_review.hits, ev.stage_a.recall_at_auto_review.n)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-500">Top candidate correct</dt>
                <dd className="tnum text-right">{ratio(ev.stage_a.top1_accuracy.value, ev.stage_a.top1_accuracy.hits, ev.stage_a.top1_accuracy.n)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-500">Needs review: correct one in top {ev.stage_a.recall_at_auto_review.review_top_k ?? 3}</dt>
                <dd className="tnum text-right">{ratio(ev.stage_a.needs_review_true_in_top3.value, ev.stage_a.needs_review_true_in_top3.hits, ev.stage_a.needs_review_true_in_top3.n)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-500">Auto-suggested but wrong</dt>
                <dd className="tnum text-right">
                  {formatNumber(ev.stage_a.wrong_auto.n)} of {formatNumber(ev.stage_a.wrong_auto.of)}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-500">Unresolved: correct one still among candidates</dt>
                <dd className="tnum text-right">
                  {formatNumber(ev.stage_a.unresolved.true_in_candidates)} of {formatNumber(ev.stage_a.unresolved.n)}
                </dd>
              </div>
            </dl>
            <div className="border-t border-line px-3 py-3">
              <div className="label-caps mb-1.5">Thresholds used</div>
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
                {Object.entries(ev.thresholds_used).map(([k, v]) => (
                  <span key={k} className="text-ink-700">
                    {THRESHOLD_LABEL[k] ?? k} <span className="mono font-medium text-ink-900">{v}</span>
                  </span>
                ))}
              </div>
            </div>
          </Panel>

          <Panel title="Relationship classification (stage B)">
            <p className="mb-3 text-sm text-ink-700">
              Pairs of cases on the same institution, classed as unrelated, duplicate, related or conflicting. N = <span className="tnum font-medium">{formatNumber(ev.stage_b.n_pairs)}</span> pairs from{' '}
              <span className="tnum">{formatNumber(ev.stage_b.n_cases)}</span> cases.
            </p>
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
              <ConfusionMatrix b={ev.stage_b} />
              <div>
                <DataTable compact caption="Per-class precision and recall" columns={classCols} rows={ev.stage_b.classes} rowKey={(c) => c.relation} />
                <div className="mt-3 rounded border border-line px-3 py-2 text-sm">
                  <div className="flex justify-between gap-3">
                    <span className="text-ink-500">Alert precision (any alert on a truly related pair)</span>
                    <span className="tnum text-right">{ratio(ev.stage_b.alert_precision.value, ev.stage_b.alert_precision.true_alerts, ev.stage_b.alert_precision.alerts)}</span>
                  </div>
                  <div className="mt-1 flex justify-between gap-3">
                    <span className="text-ink-500">Alert precision, exact relation only</span>
                    <span className="tnum text-right">{ratio(ev.stage_b.alert_precision.strict_value, [1, 2, 3].reduce((a, k) => a + (ev.stage_b.confusion_matrix[k]?.[k] ?? 0), 0), ev.stage_b.alert_precision.alerts)}</span>
                  </div>
                </div>
              </div>
            </div>
          </Panel>

          <Panel title={`Known failure cases (worst ${formatNumber(ev.failure_cases.length)} of ${formatNumber(ev.failure_total)})`} padded={false}>
            <DataTable
              caption="Known failure cases"
              columns={failCols}
              rows={failRows}
              rowKey={(f) => f.__k}
              emptyMessage="No failures on this split."
              className="rounded-none border-0"
            />
          </Panel>

          {ev.notes.length > 0 && (
            <Panel title="Method notes">
              <ul className="list-disc pl-5 text-sm text-ink-700">
                {ev.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
