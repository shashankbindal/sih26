import { api } from '@/api/client';
import { useApiMutation, useApiQuery } from '@/api/hooks';

export interface ConfigOut<T> {
  key: string;
  value: T;
  updated_at?: string | null;
  updated_by?: string | null;
}

export function useConfig<T>(key: string) {
  return useApiQuery<ConfigOut<T>>(['admin', 'config', key], `/admin/config/${key}`);
}

/** PUT /admin/config/{key} with { value }; dict keys are merged server-side, lists and scalars replaced. */
export function usePutConfig<T>(key: string) {
  return useApiMutation<ConfigOut<T>, T>((value) => api.put<ConfigOut<T>>(`/admin/config/${key}`, { value }), {
    invalidate: [['admin', 'config', key], ['policy'], ['dash']],
  });
}
