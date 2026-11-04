import { useCallback, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, Upload } from 'lucide-react';
import { Button, DataTable, EmptyState, Panel, Select, useToast, type Column } from '@/components/ui';
import { api, errorMessage } from '@/api/client';
import { useApiMutation } from '@/api/hooks';
import { cx } from '@/lib/cx';
import { formatNumber } from '@/lib/format';
import { downloadFile } from '@/features/reports/download';
import { FIELD_LABEL, type ImportJob, type ImportPreview } from './importApi';

const STEPS = ['Upload', 'Map columns', 'Preview', 'Run', 'Summary'];
const MAX_BYTES = 10 * 1024 * 1024;

function Stepper({ step }: { step: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm" aria-label="Import steps">
      {STEPS.map((s, i) => {
        const state = i < step ? 'done' : i === step ? 'current' : 'todo';
        return (
          <li key={s} className="flex items-center gap-2" aria-current={state === 'current' ? 'step' : undefined}>
            <span
              aria-hidden
              className={cx(
                'inline-flex h-5 w-5 items-center justify-center rounded-sm text-xs font-semibold tnum',
                state === 'current' && 'bg-navy text-surface',
                state === 'done' && 'bg-navy-50 text-navy',
                state === 'todo' && 'bg-neutral-bg text-ink-500',
              )}
            >
              {i + 1}
            </span>
            <span className={cx(state === 'current' ? 'font-semibold text-ink-900' : 'text-ink-500')}>{s}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** Mapping orientation used by the API: { file_column: lok_sutra_field }. */
function initialMapping(p: ImportPreview): Record<string, string> {
  const out: Record<string, string> = {};
  p.columns.forEach((c) => (out[c] = p.suggested_mapping[c] ?? ''));
  return out;
}

export default function ImportPage() {
  const { toast } = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [job, setJob] = useState<ImportJob | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const pick = useCallback((f: File | undefined | null) => {
    if (!f) return;
    setFileError(null);
    if (!/\.(csv|xlsx)$/i.test(f.name)) {
      setFileError('Choose a CSV or XLSX file.');
      return;
    }
    if (f.size > MAX_BYTES) {
      setFileError('The file is larger than 10 MB.');
      return;
    }
    setFile(f);
  }, []);

  const previewMut = useApiMutation(
    (f: File) => {
      const fd = new FormData();
      fd.append('file', f);
      return api.upload<ImportPreview>('/imports/preview', fd);
    },
    {
      onSuccess: (p) => {
        setPreview(p);
        setMapping(initialMapping(p));
        setStep(1);
      },
      onError: (e) => setFileError(`Could not read the file. ${errorMessage(e)}`),
    },
  );

  const fieldToColumn = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [col, field] of Object.entries(mapping)) if (field) out[field] = col;
    return out;
  }, [mapping]);

  const runMut = useApiMutation(
    (vars: { f: File; map: Record<string, string> }) => {
      const fd = new FormData();
      fd.append('file', vars.f);
      fd.append('mapping', JSON.stringify(vars.map));
      return api.upload<ImportJob>('/imports', fd);
    },
    {
      invalidate: [['dash'], ['cases'], ['links'], ['review']],
      onSuccess: (j) => {
        setJob(j);
        setStep(4);
      },
      onError: (e) => toast(`The import failed. ${errorMessage(e)}`, 'red'),
    },
  );

  const reset = () => {
    setStep(0);
    setFile(null);
    setPreview(null);
    setMapping({});
    setJob(null);
    setFileError(null);
    if (input.current) input.current.value = '';
  };

  // The importer requires a received date, a subject and an institution name or Permanent ID.
  const missing: string[] = [];
  if (preview) {
    if (!fieldToColumn.received_at) missing.push('Received at');
    if (!fieldToColumn.subject) missing.push('Subject');
    if (!fieldToColumn.institution_name && !fieldToColumn.permanent_id) missing.push('Institution as written or Permanent ID');
  }

  /* Step 3 table: the mapped fields only, in template order. */
  const mappedFields = preview ? preview.target_fields.filter((f) => fieldToColumn[f]) : [];
  const previewRows = (preview?.sample_rows ?? []).slice(0, 20).map((r, i) => ({ ...r, __i: String(i) }));
  const previewColumns: Column<Record<string, string>>[] = [
    { key: '#', header: '#', numeric: true, render: (_r, i) => i + 1 },
    ...mappedFields.map<Column<Record<string, string>>>((f) => ({
      key: f,
      header: FIELD_LABEL[f] ?? f,
      mono: f === 'source_ref' || f === 'permanent_id' || f === 'received_at',
      render: (r) => <span className="block max-w-[260px] truncate" title={r[fieldToColumn[f]]}>{r[fieldToColumn[f]] || '–'}</span>,
    })),
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink-900">Import cases</h1>
        <Button icon={Download} onClick={() => void downloadFile('/imports/template.csv', 'lok_sutra_import_template.csv').catch((e: unknown) => toast(`Could not download the template. ${errorMessage(e)}`, 'red'))}>
          Download template
        </Button>
      </div>
      <Stepper step={step} />

      {step === 0 && (
        <Panel title="1. Upload a CSV or Excel file">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              pick(e.dataTransfer.files[0]);
            }}
            className={cx('flex h-40 flex-col items-center justify-center gap-2 rounded border border-dashed text-sm', drag ? 'border-navy bg-navy-50' : 'border-ink-300 bg-paper')}
          >
            <Upload size={20} strokeWidth={1.75} aria-hidden className="text-ink-500" />
            <span className="text-ink-700">Drop a file here, or</span>
            <Button onClick={() => input.current?.click()}>Choose file</Button>
            <input ref={input} type="file" accept=".csv,.xlsx" className="sr-only" aria-label="Choose a CSV or XLSX file" onChange={(e) => pick(e.target.files?.[0])} />
            <span className="text-xs text-ink-500">CSV or XLSX, up to 10 MB. Imports of up to 1,000 rows run immediately.</span>
          </div>
          {fileError && <p className="mt-2 text-sm text-red">{fileError}</p>}
          {file && (
            <div className="mt-3 flex items-center justify-between rounded border border-line px-3 py-2">
              <span className="text-sm">
                <span className="mono">{file.name}</span> <span className="tnum text-ink-500">({formatNumber(Math.max(1, Math.round(file.size / 1024)))} KB)</span>
              </span>
              <Button variant="primary" loading={previewMut.isPending} onClick={() => previewMut.mutate(file)}>
                Continue
              </Button>
            </div>
          )}
          <p className="mt-3 text-xs text-ink-500">Use the template for the expected column names. All data in this prototype is synthetic.</p>
        </Panel>
      )}

      {step === 1 && preview && (
        <Panel title="2. Map columns" padded={false}>
          <p className="px-3 pt-3 text-sm text-ink-700">
            <span className="mono">{preview.filename}</span> has {formatNumber(preview.total_rows)} rows. The mapping below is suggested from the column names; change any row.
          </p>
          <table className="ls-table mt-3">
            <thead>
              <tr>
                <th scope="col">Column in your file</th>
                <th scope="col">First value</th>
                <th scope="col" style={{ width: 280 }}>
                  Lok Sutra field
                </th>
              </tr>
            </thead>
            <tbody>
              {preview.columns.map((c) => (
                <tr key={c}>
                  <td className="mono">{c}</td>
                  <td className="max-w-[320px] truncate text-ink-500">{preview.sample_rows[0]?.[c] ?? '–'}</td>
                  <td style={{ padding: '4px 12px' }}>
                    <Select aria-label={`Field for column ${c}`} value={mapping[c] ?? ''} onChange={(e) => setMapping((m) => ({ ...m, [c]: e.target.value }))}>
                      <option value="">Do not import</option>
                      {preview.target_fields.map((f) => (
                        <option key={f} value={f} disabled={!!fieldToColumn[f] && fieldToColumn[f] !== c}>
                          {FIELD_LABEL[f] ?? f}
                        </option>
                      ))}
                    </Select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between border-t border-line p-3">
            <div className="text-sm">
              {missing.length > 0 ? (
                <span className="text-red">Map a column to: {missing.join(', ')}.</span>
              ) : (
                <span className="text-ink-500">{formatNumber(Object.keys(fieldToColumn).length)} fields mapped.</span>
              )}
            </div>
            <div className="flex gap-2">
              <Button onClick={() => setStep(0)}>Back</Button>
              <Button variant="primary" disabled={missing.length > 0} onClick={() => setStep(2)}>
                Continue
              </Button>
            </div>
          </div>
        </Panel>
      )}

      {step === 2 && preview && (
        <Panel title={`3. Preview the first ${formatNumber(previewRows.length)} rows`} padded={false}>
          <p className="px-3 py-3 text-sm text-ink-700">
            {formatNumber(preview.total_rows)} rows will be read. Institution text is shown as written; matching to an institution happens when you run the import.
          </p>
          <DataTable compact caption="Import preview" columns={previewColumns} rows={previewRows} rowKey={(r) => r.__i} maxHeight={380} className="rounded-none border-x-0" />
          <div className="flex justify-end gap-2 border-t border-line p-3">
            <Button onClick={() => setStep(1)}>Back</Button>
            <Button variant="primary" onClick={() => setStep(3)}>
              Continue
            </Button>
          </div>
        </Panel>
      )}

      {step === 3 && preview && file && (
        <Panel title="4. Run the import">
          <p className="text-sm text-ink-700">
            Import <span className="tnum font-medium">{formatNumber(preview.total_rows)}</span> rows from <span className="mono">{file.name}</span>. Each row creates a case, suggests an institution and checks for related cases. Nothing is merged or changed on its own.
          </p>
          {runMut.isPending && <p className="mt-2 text-sm text-ink-500" role="status">Importing. This can take up to 30 seconds for 500 rows.</p>}
          <div className="mt-4 flex gap-2">
            <Button onClick={() => setStep(2)} disabled={runMut.isPending}>
              Back
            </Button>
            <Button variant="primary" loading={runMut.isPending} onClick={() => runMut.mutate({ f: file, map: Object.fromEntries(Object.entries(mapping).filter(([, v]) => v)) })}>
              Run import
            </Button>
          </div>
        </Panel>
      )}

      {step === 4 && job && (
        <Panel title="5. Summary">
          <p className="mb-3 text-sm text-ink-700">
            <span className="mono">{job.filename}</span>: {formatNumber(job.imported)} of {formatNumber(job.total_rows)} rows imported.
          </p>
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line md:grid-cols-3 xl:grid-cols-6">
            {[
              { k: 'Rows imported', v: job.imported },
              { k: 'Institution auto-suggested', v: job.auto_suggested },
              { k: 'Needs review', v: job.needs_review, link: '/review', text: 'Open review queue' },
              { k: 'Unresolved', v: job.unresolved },
              { k: 'Links found', v: job.links_found, link: '/coordination', text: 'Open coordination inbox', coordination: true },
              { k: 'Rows with errors', v: job.error_count },
            ].map((c) => (
              <div key={c.k} className="bg-surface px-3 py-3">
                <dt className="flex items-center gap-1.5 text-xs text-ink-500">
                  {c.coordination && <span aria-hidden className="inline-block h-2 w-2 bg-saffron" />}
                  {c.k}
                </dt>
                <dd className="mt-1 text-kpi font-semibold tnum text-ink-900">{formatNumber(c.v)}</dd>
                <div className="mt-0.5 h-4 text-xs">{c.link && c.v > 0 && <Link to={c.link}>{c.text}</Link>}</div>
              </div>
            ))}
          </dl>
          {job.error_count > 0 && (
            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink-900">Rows that could not be imported</h3>
                <Button icon={Download} onClick={() => void downloadFile(`/imports/${job.id}/errors.csv`, `import_${job.id}_errors.csv`).catch((e: unknown) => toast(`Could not download the errors. ${errorMessage(e)}`, 'red'))}>
                  Download errors CSV
                </Button>
              </div>
              <DataTable
                compact
                caption="Import errors"
                columns={[
                  { key: 'row', header: 'Row', numeric: true, render: (e) => formatNumber(e.row) },
                  { key: 'message', header: 'Problem', render: (e) => e.message },
                ]}
                rows={job.errors.slice(0, 20)}
                rowKey={(e) => `${e.row}-${e.message}`}
                maxHeight={260}
              />
              {job.errors.length > 20 && <p className="mt-1 text-xs text-ink-500">Showing 20 of {formatNumber(job.errors.length)}. The CSV has all of them.</p>}
            </div>
          )}
          {job.error_count === 0 && job.imported === 0 && <EmptyState message="No rows were imported." />}
          <div className="mt-4 flex gap-2">
            <Button variant="primary" onClick={reset}>
              Import another file
            </Button>
            <Link to="/cases" className="inline-flex h-ctl items-center text-sm">
              Open case register
            </Link>
          </div>
        </Panel>
      )}
    </div>
  );
}
