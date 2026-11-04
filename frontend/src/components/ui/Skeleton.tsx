import { cx } from '@/lib/cx';

/** Grey bar matching the layout it stands in for. Never use spinners for content. */
export function Skeleton({ className, width, height = 12 }: { className?: string; width?: number | string; height?: number | string }) {
  return <div aria-hidden className={cx('skeleton', className)} style={{ width: width ?? '100%', height }} />;
}

export function SkeletonRows({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div role="status" aria-label="Loading" className="divide-y divide-line-soft">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex h-row items-center gap-4 px-3">
          {Array.from({ length: cols }).map((__, c) => (
            <Skeleton key={c} width={c === 0 ? 96 : `${60 + ((r * 7 + c * 13) % 35)}%`} />
          ))}
        </div>
      ))}
    </div>
  );
}
