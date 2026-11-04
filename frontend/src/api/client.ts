import { API_BASE } from '@/lib/env';
import { getToken } from './token';

export interface ApiErrorBody {
  error?: { code?: string; message?: string; details?: Record<string, unknown> };
}

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
  get isNotFound(): boolean {
    return this.status === 404;
  }
}

type Params = Record<string, string | number | boolean | null | undefined | ReadonlyArray<string | number>>;

export interface RequestOptions {
  params?: Params;
  body?: unknown;
  signal?: AbortSignal;
  /** Skip the bearer header (login, health). */
  anonymous?: boolean;
  /** Raw FormData body (imports). Content-Type is left to the browser. */
  formData?: FormData;
  /** Return the Response body as a Blob (PDF/CSV downloads). */
  blob?: boolean;
}

let onUnauthorized: (() => void) | null = null;
/** AuthContext registers this so a 401 anywhere signs the user out and redirects to /login. */
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

export function buildUrl(path: string, params?: Params): string {
  const url = new URL(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === '') continue;
      if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, String(x)));
      else url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

const RETRY_STATUS = new Set([502, 503, 504]);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function parseError(res: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null;
  try {
    body = (await res.json()) as ApiErrorBody;
  } catch {
    body = null;
  }
  const e = body?.error;
  return new ApiError(res.status, e?.code ?? `HTTP_${res.status}`, e?.message ?? res.statusText ?? 'Request failed', e?.details ?? {});
}

export async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const token = opts.anonymous ? null : getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.formData) body = opts.formData;
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  const url = buildUrl(path, opts.params);
  const idempotent = method === 'GET' || method === 'HEAD';

  const attempt = async (): Promise<Response> => fetch(url, { method, headers, body, signal: opts.signal });

  let res: Response;
  try {
    res = await attempt();
    if (idempotent && RETRY_STATUS.has(res.status)) {
      await sleep(800);
      res = await attempt();
    }
  } catch (err) {
    if (opts.signal?.aborted) throw err;
    if (!idempotent) throw new ApiError(0, 'NETWORK_ERROR', 'The server could not be reached.');
    await sleep(800);
    try {
      res = await attempt();
    } catch {
      throw new ApiError(0, 'NETWORK_ERROR', 'The server could not be reached.');
    }
  }

  if (!res.ok) {
    if (res.status === 401 && !opts.anonymous && onUnauthorized) onUnauthorized();
    throw await parseError(res);
  }
  if (res.status === 204) return undefined as T;
  if (opts.blob) return (await res.blob()) as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, 'body' | 'formData'>) => request<T>('GET', path, opts),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'body'>) => request<T>('POST', path, { ...opts, body }),
  put: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'body'>) => request<T>('PUT', path, { ...opts, body }),
  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'body'>) => request<T>('PATCH', path, { ...opts, body }),
  del: <T>(path: string, opts?: RequestOptions) => request<T>('DELETE', path, opts),
  upload: <T>(path: string, formData: FormData, opts?: Omit<RequestOptions, 'formData'>) => request<T>('POST', path, { ...opts, formData }),
};

/** Human message for toasts and error panels. Never includes PII. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return 'Something went wrong.';
}

/* ------------------------------------------------------------------ */
/* Server warm-up: /health with exponential backoff (1, 2, 4, 8 s ... up to 90 s) */
/* ------------------------------------------------------------------ */

export type ServerStatus = 'checking' | 'connecting' | 'ready' | 'unreachable';
let serverStatus: ServerStatus = 'checking';
const listeners = new Set<() => void>();
function setStatus(s: ServerStatus) {
  if (s === serverStatus) return;
  serverStatus = s;
  listeners.forEach((l) => l());
}
export const serverStatusStore = {
  subscribe(l: () => void) {
    listeners.add(l);
    return () => listeners.delete(l);
  },
  getSnapshot: () => serverStatus,
};

let warmStarted = false;
export function startWarmUp(): void {
  if (warmStarted) return;
  warmStarted = true;
  const began = Date.now();
  const SHOW_AFTER_MS = 1200;
  const MAX_MS = 90_000;
  let delay = 1000;
  const showTimer = window.setTimeout(() => {
    if (serverStatus === 'checking') setStatus('connecting');
  }, SHOW_AFTER_MS);

  const tick = async (): Promise<void> => {
    try {
      const ctl = new AbortController();
      const t = window.setTimeout(() => ctl.abort(), 20_000);
      const res = await fetch(buildUrl('/health'), { signal: ctl.signal });
      window.clearTimeout(t);
      if (res.ok) {
        window.clearTimeout(showTimer);
        setStatus('ready');
        return;
      }
    } catch {
      /* fall through to retry */
    }
    if (Date.now() - began > MAX_MS) {
      window.clearTimeout(showTimer);
      setStatus('unreachable');
      return;
    }
    if (serverStatus === 'checking') setStatus('connecting');
    await sleep(delay);
    delay = Math.min(delay * 2, 8000);
    return tick();
  };
  void tick();
}

/** Allow a manual retry from the banner. */
export function retryWarmUp(): void {
  warmStarted = false;
  setStatus('checking');
  startWarmUp();
}
