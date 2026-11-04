import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown } from 'lucide-react';
import { api } from '@/api/client';
import type { Schemas } from '@/api/types';
import { useApiMutation } from '@/api/hooks';
import { useAuth } from '@/auth';
import { InstitutionCard, MatchStatusTag, ReasonList } from '@/components/domain';
import { Badge, Button, DropdownMenu, Field, Input, Panel, Select, Skeleton, Tabs, Textarea, useToast } from '@/components/ui';
import { CATEGORY_LABEL, CHANNEL_LABEL, BUREAU_LABEL, type Bureau, type CaseCategory, type SourceChannel } from '@/lib/constants';
import { DEMO_MODE } from '@/lib/env';
import { ICON } from '@/lib/icons';
import { DEMO_INPUTS } from './demoInputs';
import { ResultPanel } from './ResultPanel';
import { InlineError, OWNER_BUREAUS, PageHeader, RO_CHOICES, ScoreBar, errText, hasDevanagari, type CaseCreate, type CaseCreateResult, type ResolveResult } from './shared';

type ParseEmailResult = Schemas['ParseEmailResult'];
type PartyType = 'STUDENT' | 'PARENT' | 'FACULTY' | 'ANONYMOUS' | 'OTHER';

const CHANNELS: SourceChannel[] = ['CSS', 'CPGRAMS', 'EMAIL', 'RO_REGISTER', 'BUREAU_FILE'];
const PARTY_LABEL: Record<PartyType, string> = { STUDENT: 'Student', PARENT: 'Parent', FACULTY: 'Faculty', ANONYMOUS: 'Anonymous', OTHER: 'Other' };

interface FormState {
  source_channel: SourceChannel;
  source_ref: string;
  received_at: string; // datetime-local, IST wall clock; empty = now
  institution_text_raw: string;
  permanent_id_raw: string;
  name: string;
  email: string;
  phone: string;
  party_type: PartyType;
  subject: string;
  description: string;
  owner_bureau: Bureau;
  owner_ro_code: string;
}

const blank = (bureau: Bureau): FormState => ({
  source_channel: 'CSS',
  source_ref: '',
  received_at: '',
  institution_text_raw: '',
  permanent_id_raw: '',
  name: '',
  email: '',
  phone: '',
  party_type: 'STUDENT',
  subject: '',
  description: '',
  owner_bureau: bureau === 'ADMIN' ? 'PGRC' : bureau,
  owner_ro_code: '',
});

function fromPayload(p: CaseCreate, fallbackBureau: Bureau): FormState {
  const base = blank(fallbackBureau);
  return {
    ...base,
    source_channel: p.source_channel as SourceChannel,
    source_ref: p.source_ref ?? '',
    institution_text_raw: p.institution_text_raw ?? '',
    permanent_id_raw: p.permanent_id_raw ?? '',
    name: p.complainant?.name ?? '',
    email: p.complainant?.email ?? '',
    phone: p.complainant?.phone ?? '',
    party_type: (p.complainant?.party_type ?? 'OTHER') as PartyType,
    subject: p.subject ?? '',
    description: p.description ?? '',
    owner_bureau: (p.owner_bureau ?? base.owner_bureau) as Bureau,
    owner_ro_code: p.owner_ro_code ?? '',
  };
}

/** datetime-local (IST wall clock) -> ISO UTC. */
function istToIso(local: string): string | undefined {
  if (!local) return undefined;
  const d = new Date(`${local}:00+05:30`);
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
}

function toPayload(f: FormState): CaseCreate {
  const clean = (s: string) => (s.trim() ? s.trim() : null);
  return {
    source_channel: f.source_channel,
    source_ref: clean(f.source_ref),
    received_at: istToIso(f.received_at) ?? null,
    institution_text_raw: clean(f.institution_text_raw),
    permanent_id_raw: clean(f.permanent_id_raw),
    complainant: { name: clean(f.name), email: clean(f.email), phone: clean(f.phone), party_type: f.party_type },
    category: null,
    subject: f.subject.trim(),
    description: clean(f.description),
    owner_bureau: f.owner_bureau,
    owner_ro_code: f.owner_bureau === 'RO' ? clean(f.owner_ro_code) : null,
  };
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Live dry-run (nothing is saved): institution suggestion and category. */
function LivePreview({ form }: { form: FormState }) {
  const key = useDebounced(
    JSON.stringify([form.institution_text_raw, form.permanent_id_raw, form.subject, form.description, form.email]),
    650,
  );
  const enabled = form.institution_text_raw.trim().length >= 3 || form.permanent_id_raw.trim().length >= 5;
  const q = useQuery<ResolveResult, Error>({
    queryKey: ['intake', 'resolve', key],
    queryFn: ({ signal }) => {
      const [institution_text_raw, permanent_id_raw, subject, description, email] = JSON.parse(key) as string[];
      return api.post<ResolveResult>(
        '/intake/resolve',
        {
          institution_text_raw: institution_text_raw || null,
          permanent_id_raw: permanent_id_raw || null,
          subject: subject || null,
          description: description || null,
          complainant_email: email || null,
        },
        { signal },
      );
    },
    enabled,
    staleTime: 30_000,
    retry: false,
  });

  return (
    <Panel title="Resolution" actions={<span className="text-xs font-normal text-ink-500">Live suggestion, not saved</span>}>
      {!enabled && (
        <p className="m-0 text-sm text-ink-500">
          Enter the institution as written (or a Permanent ID) and the suggested institution, score and reasons appear here before you save.
        </p>
      )}
      {enabled && (q.isLoading || (q.isFetching && !q.data)) && (
        <div className="flex flex-col gap-2" role="status" aria-label="Resolving">
          <Skeleton height={44} />
          <Skeleton height={12} width="70%" />
          <Skeleton height={12} width="55%" />
        </div>
      )}
      {enabled && q.isError && <InlineError>{errText(q.error)}</InlineError>}
      {enabled && q.data && <PreviewBody data={q.data} />}
    </Panel>
  );
}

function PreviewBody({ data }: { data: ResolveResult }) {
  const r = data.resolution;
  const sel = r.selected;
  const top = r.candidates[0];
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-500">
        {r.status === 'EXACT' ? <Badge tone="ok">Permanent ID exact</Badge> : <MatchStatusTag status={r.status} />}
        {data.normalised_text && (
          <span>
            Normalised: <span className="font-mono text-ink-700">{data.normalised_text}</span>
          </span>
        )}
      </div>
      {sel ? (
        <InstitutionCard institution={{ id: sel.institution_id, name: sel.name, permanent_id: sel.permanent_id, district: sel.district, state: sel.state }} linked={false}>
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-3">
              <span className="label-caps text-ink-500">Match score</span>
              <ScoreBar score={sel.score} width={180} />
            </div>
            {top && <ReasonList reasons={top.reasons} />}
          </div>
        </InstitutionCard>
      ) : (
        <div className="text-sm text-ink-700">
          No confident match yet.
          {top && (
            <div className="mt-2 text-xs text-ink-500">
              Closest: <span className="text-ink-900">{top.name}</span> <span className="font-mono tnum">{top.score.toFixed(2)}</span>
            </div>
          )}
        </div>
      )}
      {r.status === 'NEEDS_REVIEW' && r.candidates.length > 1 && (
        <div>
          <div className="label-caps mb-1 text-ink-500">Candidates</div>
          <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm">
            {r.candidates.slice(0, 3).map((c) => (
              <li key={c.institution_id} className="flex items-center justify-between gap-3">
                <span className="truncate">{c.name}</span>
                <ScoreBar score={c.score} width={96} />
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="border-t border-line-soft pt-2 text-sm text-ink-700">
        Category suggestion:{' '}
        <span className="font-semibold text-ink-900">{CATEGORY_LABEL[data.category_suggestion.category as CaseCategory]}</span>
        {data.category_suggestion.keywords.length > 0 && <span className="text-xs text-ink-500"> (keywords: {data.category_suggestion.keywords.join(', ')})</span>}
      </div>
    </div>
  );
}

/** Compact read-only record of what was submitted; the result panel carries the outcome. */
function SubmittedSummary({ form, caseId, displayId }: { form: FormState; caseId: string; displayId: string }) {
  const rows: Array<[string, ReactNode]> = [
    ['Channel', `${CHANNEL_LABEL[form.source_channel]}${form.source_ref ? ` · ${form.source_ref}` : ''}`],
    ['Institution as written', <span key="i" lang={hasDevanagari(form.institution_text_raw) ? 'hi' : undefined}>{form.institution_text_raw || 'Not provided'}</span>],
    ['Subject', <span key="s" lang={hasDevanagari(form.subject) ? 'hi' : undefined}>{form.subject}</span>],
    ['Description', <span key="d" className="whitespace-pre-wrap">{form.description || 'None'}</span>],
    ['Complainant', [form.name, PARTY_LABEL[form.party_type]].filter(Boolean).join(' · ') || 'Not provided'],
    ['Owner bureau', BUREAU_LABEL[form.owner_bureau]],
  ];
  return (
    <Panel title="Submitted" actions={<Link to={`/cases/${caseId}`} className="font-mono text-xs tnum">{displayId}</Link>}>
      <dl className="m-0 flex flex-col gap-3 text-sm">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt className="label-caps text-ink-500">{k}</dt>
            <dd className="m-0 mt-0.5 break-words text-ink-900">{v}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

function PasteEmail({ onParsed }: { onParsed: (r: ParseEmailResult) => void }) {
  const [raw, setRaw] = useState('');
  const [error, setError] = useState<string | null>(null);
  const parse = useApiMutation<ParseEmailResult, string>((raw_text) => api.post<ParseEmailResult>('/intake/parse-email', { raw_text }), {
    onSuccess: onParsed,
    onError: (e) => setError(errText(e)),
  });
  return (
    <Panel title="Paste email" className="max-w-3xl">
      <Field label="Raw email text" hint="Include the From, Subject and body lines. The subject, sender, institution mention, Permanent ID and references are extracted into the case form for you to review.">
        <Textarea rows={14} value={raw} onChange={(e) => setRaw(e.target.value)} className="font-mono !text-xs" placeholder={'From: ...\nSubject: ...\n\n...'} />
      </Field>
      {error && <div className="mt-2"><InlineError>{error}</InlineError></div>}
      <div className="mt-3 flex items-center gap-2">
        <Button
          variant="primary"
          loading={parse.isPending}
          disabled={raw.trim().length < 10}
          onClick={() => {
            setError(null);
            parse.mutate(raw);
          }}
        >
          Parse email
        </Button>
        <span className="text-xs text-ink-500">Nothing is saved until you review and save the case.</span>
      </div>
    </Panel>
  );
}

export default function NewCasePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();
  const bureau = (user?.bureau ?? 'PGRC') as Bureau;
  const [tab, setTab] = useState<'manual' | 'email'>('manual');
  const [form, setForm] = useState<FormState>(() => blank(bureau));
  const [result, setResult] = useState<CaseCreateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const topRef = useRef<HTMLDivElement>(null);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((f) => ({ ...f, [k]: v }));

  const save = useApiMutation<CaseCreateResult, CaseCreate>((body) => api.post<CaseCreateResult>('/cases', body), {
    onSuccess: (res) => {
      setResult(res);
      setError(null);
      toast(`Case ${res.case.display_id} saved.`, 'ok');
      window.setTimeout(() => topRef.current?.scrollIntoView({ block: 'start' }), 0);
      for (const k of ['cases', 'case', 'institution', 'links', 'review', 'count', 'dashboard']) void qc.invalidateQueries({ queryKey: [k] });
    },
    onError: (e) => setError(errText(e)),
  });

  const subjectMissing = touched && form.subject.trim().length === 0;
  const onSave = () => {
    setTouched(true);
    if (!form.subject.trim()) return;
    setError(null);
    save.mutate(toPayload(form));
  };

  const text = `${form.subject} ${form.description}`;
  const langTag = useMemo(() => {
    if (!text.trim()) return null;
    if (hasDevanagari(text)) return /[A-Za-z]{4,}/.test(form.description) ? 'Hinglish' : 'Hindi';
    return /\b(maine|nahi|nahin|wapas|abhi|tak|hai|hain|ko|bolta|kiya)\b/i.test(text) ? 'Hinglish' : 'English';
  }, [text, form.description]);

  const reset = () => {
    setResult(null);
    setForm(blank(bureau));
    setTouched(false);
    setNote(null);
    setError(null);
  };

  const demoItems = DEMO_INPUTS.map((d) => ({
    key: d.key,
    label: d.label,
    onSelect: () => {
      setResult(null);
      setForm(fromPayload(d.payload, bureau));
      setTab('manual');
      setTouched(false);
      setNote(`Demo input loaded: ${d.label}.`);
    },
  }));

  return (
    <div ref={topRef} className="scroll-mt-4">
      <PageHeader
        title="New case"
        subtitle="Record a complaint from any channel. On save the institution is resolved and related cases are suggested for your decision."
        actions={
          DEMO_MODE && !result ? (
            <DropdownMenu
              align="right"
              width={380}
              items={demoItems}
              trigger={({ open, toggle }) => (
                <Button aria-haspopup="menu" aria-expanded={open} onClick={toggle}>
                  Demo inputs
                  <ChevronDown {...ICON} />
                </Button>
              )}
            />
          ) : undefined
        }
      />

      <Tabs
        ariaLabel="Intake method"
        className="mb-4"
        tabs={[
          { id: 'manual', label: 'Manual entry' },
          { id: 'email', label: 'Paste email' },
          { id: 'import', label: 'Import file' },
        ]}
        value={tab}
        onChange={(id) => {
          if (id === 'import') navigate('/import');
          else setTab(id as 'manual' | 'email');
        }}
      />

      {tab === 'email' && !result && (
        <PasteEmail
          onParsed={(r) => {
            setForm(fromPayload(r.prefill, bureau));
            setTab('manual');
            setTouched(false);
            setNote('Prefilled from the pasted email. Review each field before saving.');
          }}
        />
      )}

      {tab === 'manual' && (
        <div className="grid items-start gap-4" style={{ gridTemplateColumns: result ? 'minmax(0, 2fr) minmax(0, 3fr)' : 'minmax(0, 3fr) minmax(0, 2fr)' }}>
          {result && <SubmittedSummary form={form} caseId={result.case.id} displayId={result.case.display_id} />}
          <form
            style={result ? { display: 'none' } : undefined}
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              onSave();
            }}
            aria-label="New case form"
          >
            {note && <div className="rounded border border-info bg-info-bg px-3 py-2 text-sm text-info">{note}</div>}
            <fieldset disabled={!!result} className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
              <Panel title="Source">
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Channel" required>
                    <Select value={form.source_channel} onChange={(e) => set('source_channel', e.target.value as SourceChannel)}>
                      {CHANNELS.map((c) => (
                        <option key={c} value={c}>
                          {CHANNEL_LABEL[c]}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Reference number">
                    <Input mono value={form.source_ref} onChange={(e) => set('source_ref', e.target.value)} placeholder="CSS-2026-00000" />
                  </Field>
                  <Field label="Received at (IST)" hint="Blank means now.">
                    <Input type="datetime-local" value={form.received_at} onChange={(e) => set('received_at', e.target.value)} />
                  </Field>
                </div>
              </Panel>

              <Panel title="Institution as written">
                <div className="grid grid-cols-[1fr_200px] gap-3">
                  <Field label="Institution name and place, as the complainant wrote it" hint="Hindi, English or mixed. No Permanent ID is needed.">
                    <Input lang={hasDevanagari(form.institution_text_raw) ? 'hi' : undefined} value={form.institution_text_raw} onChange={(e) => set('institution_text_raw', e.target.value)} />
                  </Field>
                  <Field label="Permanent ID (optional)">
                    <Input mono value={form.permanent_id_raw} onChange={(e) => set('permanent_id_raw', e.target.value)} placeholder="1-0000000000" />
                  </Field>
                </div>
              </Panel>

              <Panel title="Complainant">
                <div className="grid grid-cols-4 gap-3">
                  <Field label="Name" className="col-span-2">
                    <Input value={form.name} onChange={(e) => set('name', e.target.value)} autoComplete="off" />
                  </Field>
                  <Field label="Type">
                    <Select value={form.party_type} onChange={(e) => set('party_type', e.target.value as PartyType)}>
                      {(Object.keys(PARTY_LABEL) as PartyType[]).map((k) => (
                        <option key={k} value={k}>
                          {PARTY_LABEL[k]}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Phone">
                    <Input mono value={form.phone} onChange={(e) => set('phone', e.target.value)} autoComplete="off" />
                  </Field>
                  <Field label="Email" className="col-span-4">
                    <Input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} autoComplete="off" />
                  </Field>
                </div>
              </Panel>

              <Panel title="Complaint" actions={langTag ? <Badge tone="neutral">Language: {langTag}</Badge> : undefined}>
                <div className="flex flex-col gap-3">
                  <Field label="Subject" required error={subjectMissing ? 'Subject is required.' : undefined}>
                    <Input lang={hasDevanagari(form.subject) ? 'hi' : undefined} value={form.subject} onChange={(e) => set('subject', e.target.value)} />
                  </Field>
                  <Field label="Description" hint="Hindi, English or Hinglish. Personal details are masked before text matching.">
                    <Textarea lang={hasDevanagari(form.description) ? 'hi' : undefined} rows={5} value={form.description} onChange={(e) => set('description', e.target.value)} />
                  </Field>
                </div>
              </Panel>

              <Panel title="Routing">
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Owner bureau" required>
                    <Select value={form.owner_bureau} onChange={(e) => set('owner_bureau', e.target.value as Bureau)}>
                      {OWNER_BUREAUS.map((b) => (
                        <option key={b} value={b}>
                          {BUREAU_LABEL[b]}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Regional Office" hint={form.owner_bureau === 'RO' ? undefined : 'Only for RO-owned cases.'}>
                    <Select value={form.owner_ro_code} disabled={form.owner_bureau !== 'RO'} onChange={(e) => set('owner_ro_code', e.target.value)}>
                      <option value="">Not set</option>
                      {RO_CHOICES.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label} ({r.value})
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
              </Panel>
            </fieldset>

            {error && <InlineError>{error}</InlineError>}
            {!result && (
              <div className="flex items-center gap-3">
                <Button type="submit" variant="primary" loading={save.isPending}>
                  Save case
                </Button>
                <Button onClick={reset} disabled={save.isPending}>
                  Clear form
                </Button>
              </div>
            )}
          </form>

          <div className={`flex min-w-0 flex-col gap-3 ${result ? '' : 'sticky top-4'}`}>
            {result ? <ResultPanel result={result} onReset={reset} /> : <LivePreview form={form} />}
          </div>
        </div>
      )}
    </div>
  );
}
