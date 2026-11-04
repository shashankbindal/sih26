import { useParams } from 'react-router-dom';

/** Stand-in for routes that do not have a screen yet. */
export function Placeholder({ title, note }: { title: string; note?: string }) {
  const params = useParams();
  const keys = Object.entries(params);
  return (
    <div>
      <h1 className="text-xl font-semibold text-ink-900">{title}</h1>
      <p className="mt-2 text-sm text-ink-500">
        {note ?? 'This screen is not built yet.'}
        {keys.length > 0 && (
          <span className="ml-2 font-mono text-xs tnum text-ink-700">
            {keys.map(([k, v]) => `${k}=${v}`).join('  ')}
          </span>
        )}
      </p>
    </div>
  );
}
