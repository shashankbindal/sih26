// Thin re-export of generated OpenAPI types. Feature code should use these instead of
// declaring duplicates:  type CaseDetail = Schemas['CaseDetail'];
import type { components, paths } from './schema';

export type Schemas = components['schemas'];
export type ApiPaths = paths;

/** Standard list envelope from the API specification: { items, total, page, page_size }. */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
