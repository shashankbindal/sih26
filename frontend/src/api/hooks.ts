import { useMutation, useQuery, useQueryClient, type QueryKey, type UseMutationOptions } from '@tanstack/react-query';
import { useSyncExternalStore } from 'react';
import { api, ApiError, serverStatusStore, type ServerStatus } from './client';

type Params = Record<string, string | number | boolean | null | undefined | ReadonlyArray<string | number>>;

export interface UseApiQueryOptions {
  params?: Params;
  enabled?: boolean;
  /** ms; e.g. 60_000 dashboard, 10_000 clearance polling. */
  refetchInterval?: number | false;
  staleTime?: number;
}

/** GET wrapper over TanStack Query. The query key is [...key, params]. */
export function useApiQuery<T>(key: QueryKey, path: string, opts: UseApiQueryOptions = {}) {
  return useQuery<T, ApiError>({
    queryKey: [...key, opts.params ?? {}],
    queryFn: ({ signal }) => api.get<T>(path, { params: opts.params, signal }),
    enabled: opts.enabled,
    refetchInterval: opts.refetchInterval,
    staleTime: opts.staleTime,
  });
}

/** Mutation wrapper: calls fn, then invalidates the given query-key prefixes. */
export function useApiMutation<TData, TVars>(
  fn: (vars: TVars) => Promise<TData>,
  opts: { invalidate?: QueryKey[] } & Omit<UseMutationOptions<TData, ApiError, TVars>, 'mutationFn'> = {},
) {
  const qc = useQueryClient();
  const { invalidate, onSuccess, ...rest } = opts;
  return useMutation<TData, ApiError, TVars>({
    mutationFn: fn,
    ...rest,
    onSuccess: (data, vars, ctx, meta) => {
      invalidate?.forEach((k) => void qc.invalidateQueries({ queryKey: k }));
      return onSuccess?.(data, vars, ctx, meta);
    },
  });
}

/** Live server warm-up status from /health. */
export function useServerStatus(): ServerStatus {
  return useSyncExternalStore(serverStatusStore.subscribe, serverStatusStore.getSnapshot);
}

/** Pulls a total out of {items,total}, {items}, or a bare array. */
export function extractTotal(data: unknown): number | undefined {
  if (Array.isArray(data)) return data.length;
  if (data && typeof data === 'object') {
    const d = data as { total?: unknown; items?: unknown };
    if (typeof d.total === 'number') return d.total;
    if (Array.isArray(d.items)) return d.items.length;
  }
  return undefined;
}

/** Count badge source that tolerates a missing endpoint (404/501) and any other error. */
export function useCount(key: string, path: string, params: Params, enabled = true): number | undefined {
  const q = useQuery<number | null, ApiError>({
    queryKey: ['count', key, params],
    queryFn: async ({ signal }) => {
      try {
        return extractTotal(await api.get<unknown>(path, { params: { ...params, page_size: 1 }, signal })) ?? null;
      } catch (e) {
        if (e instanceof ApiError && e.status < 500 && e.status !== 0) return null;
        throw e;
      }
    },
    enabled,
    refetchInterval: 60_000,
    retry: false,
  });
  return q.data ?? undefined;
}

export interface PolicyThresholds {
  /** inst_review: below this an institution match is unresolved; at or above, needs review. */
  review?: number;
  /** inst_auto: at or above, auto-suggested. */
  auto?: number;
  dup?: number;
  related?: number;
}

/**
 * Thresholds come from policy_config (never hard-coded). Tolerates a missing or forbidden endpoint:
 * returns undefined and the ScoreMeter then omits tick marks rather than inventing values.
 */
export function usePolicyThresholds(enabled = true): PolicyThresholds | undefined {
  const q = useQuery<PolicyThresholds | undefined, ApiError>({
    queryKey: ['policy', 'thresholds'],
    queryFn: async ({ signal }) => {
      try {
        const raw = await api.get<Record<string, unknown>>('/admin/config/thresholds', { signal });
        const v = ((raw && typeof raw === 'object' && 'value' in raw ? raw.value : raw) ?? {}) as Record<string, number>;
        return { review: v.inst_review, auto: v.inst_auto, dup: v.dup, related: v.related };
      } catch (e) {
        if (e instanceof ApiError && e.status < 500 && e.status !== 0) return undefined;
        throw e;
      }
    },
    enabled,
    staleTime: Infinity,
    retry: false,
  });
  return q.data;
}
