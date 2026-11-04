import { api } from '@/api/client';
import { CASE_STATUS_LABEL, CATEGORY_LABEL, CHANNEL_LABEL, PENDING_STEP_LABEL, type CaseCategory, type CaseStatus, type PendingStep, type SourceChannel } from '@/lib/constants';
import { formatDateTime } from '@/lib/format';
import { toApiParams, type CaseFilters } from './filters';
import type { CaseListPage, CaseSummary } from './shared';

export const EXPORT_LIMIT = 1000;
const EXPORT_PAGE = 200;

const HEADERS = [
  'Case ID',
  'Received (IST)',
  'Channel',
  'Institution',
  'Permanent ID',
  'Category',
  'Owner bureau',
  'Owner officer',
  'Status',
  'Pending step',
  'Pending since (IST)',
  'Clocks',
  'Open alerts',
];

/** Quote a cell; neutralise spreadsheet formulas (=, +, -, @) so exported text cannot execute. */
function cell(v: string): string {
  const safe = /^[=+\-@\t\r]/.test(v) ? `'${v}` : v;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

function row(c: CaseSummary): string[] {
  return [
    c.display_id,
    formatDateTime(c.received_at),
    CHANNEL_LABEL[c.source_channel as SourceChannel] ?? c.source_channel,
    c.institution?.name ?? c.institution_text_raw ?? '',
    c.institution?.permanent_id ?? '',
    CATEGORY_LABEL[c.category as CaseCategory] ?? c.category,
    c.owner_bureau + (c.owner_ro_code ? ` (${c.owner_ro_code})` : ''),
    c.owner_officer?.name ?? '',
    CASE_STATUS_LABEL[c.status as CaseStatus] ?? c.status,
    PENDING_STEP_LABEL[c.pending_step as PendingStep] ?? c.pending_step,
    c.pending_since ? formatDateTime(c.pending_since) : '',
    c.clocks.map((k) => k.label).join(' | '),
    String(c.alerts.total),
  ];
}

export interface ExportResult {
  rows: number;
  total: number;
  truncated: boolean;
}

/** Pages through GET /cases with the current filters (up to EXPORT_LIMIT rows) and downloads a CSV. */
export async function exportCasesCsv(filters: CaseFilters, onProgress?: (done: number) => void): Promise<ExportResult> {
  const items: CaseSummary[] = [];
  let total = 0;
  for (let page = 1; items.length < EXPORT_LIMIT; page++) {
    const res = await api.get<CaseListPage>('/cases', { params: toApiParams(filters, page, EXPORT_PAGE) });
    total = res.total;
    items.push(...res.items);
    onProgress?.(items.length);
    if (res.items.length < EXPORT_PAGE || items.length >= res.total) break;
  }
  const used = items.slice(0, EXPORT_LIMIT);
  const lines = [HEADERS, ...used.map(row)].map((r) => r.map(cell).join(','));
  // BOM so Excel reads UTF-8 (Devanagari institution text).
  const blob = new Blob(['﻿', lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `lok-sutra-cases-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return { rows: used.length, total, truncated: total > used.length };
}
