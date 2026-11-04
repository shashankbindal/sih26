import { api } from '@/api/client';

type Params = Record<string, string | number | boolean | null | undefined | ReadonlyArray<string | number>>;

/** Saves a Blob through a temporary anchor (works for authenticated downloads). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Authenticated GET (bearer header) streamed to a file download. */
export async function downloadFile(path: string, filename: string, params?: Params): Promise<void> {
  const blob = await api.get<Blob>(path, { params, blob: true });
  saveBlob(blob, filename);
}
