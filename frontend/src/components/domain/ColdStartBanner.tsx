import { useServerStatus } from '@/api/hooks';
import { retryWarmUp } from '@/api/client';

/** Top of content. Shows while /health has not answered; auto-hides when it does. */
export function ColdStartBanner({ forceVisible }: { forceVisible?: boolean }) {
  const status = useServerStatus();
  if (!forceVisible && status !== 'connecting' && status !== 'unreachable') return null;
  const unreachable = !forceVisible && status === 'unreachable';
  return (
    <div role="status" className="border-b border-line bg-info-bg text-info">
      <div className="flex items-center justify-between gap-4 px-6 py-2 text-sm">
        <span>
          {unreachable
            ? 'The server did not respond. Check that the API is running, then retry.'
            : 'Connecting to the server. The first request after idle can take up to a minute.'}
        </span>
        {unreachable && (
          <button type="button" onClick={retryWarmUp} className="focus-ring text-info underline" style={{ background: 'none', border: 0, font: 'inherit' }}>
            Retry
          </button>
        )}
      </div>
      {!unreachable && (
        <div className="progress-line" aria-hidden>
          <span />
        </div>
      )}
    </div>
  );
}
