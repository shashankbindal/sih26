// Shapes follow backend/app/schemas/reporting.py (ImportPreview, ImportJobOut).
export interface ImportPreview {
  filename: string;
  columns: string[];
  sample_rows: Record<string, string>[];
  total_rows: number;
  suggested_mapping: Record<string, string>;
  target_fields: string[];
}
export interface ImportRowError {
  row: number;
  message: string;
}
export interface ImportJob {
  id: string;
  filename: string;
  status: string;
  mapping: Record<string, string>;
  total_rows: number;
  imported: number;
  auto_suggested: number;
  needs_review: number;
  unresolved: number;
  links_found: number;
  error_count: number;
  errors: ImportRowError[];
  created_at: string;
  finished_at?: string | null;
}

/** Plain-language names for the template fields. */
export const FIELD_LABEL: Record<string, string> = {
  source_channel: 'Source channel',
  source_ref: 'Source reference',
  received_at: 'Received at',
  institution_name: 'Institution as written',
  permanent_id: 'Permanent ID',
  complainant_name: 'Complainant name',
  complainant_email: 'Complainant email',
  complainant_phone: 'Complainant phone',
  category: 'Category',
  subject: 'Subject',
  description: 'Description',
  owner_bureau: 'Owner bureau',
  ro_code: 'Regional Office code',
  status: 'Status',
  pending_step: 'Pending step',
};
