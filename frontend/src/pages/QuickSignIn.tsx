import { ChevronRight } from 'lucide-react';
import { cx } from '@/lib/cx';
import { ICON } from '@/lib/icons';
import { bureauColour, DEMO_PASSWORD, roleLabel, splitUsers, type DemoUser } from './demoUsers';

function Pick({ user, disabled, active, onPick }: { user: DemoUser; disabled: boolean; active: boolean; onPick: (u: DemoUser) => void }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onPick(user)}
      className={cx(
        'focus-ring flex min-h-[48px] w-full flex-col justify-center rounded border border-line border-l-4 bg-surface px-3 py-1.5 text-left hover:bg-navy-50 disabled:cursor-not-allowed disabled:opacity-60',
        active && 'bg-navy-50',
      )}
      style={{ borderLeftColor: bureauColour(user) }}
    >
      <span className="text-2xs font-semibold uppercase tracking-[0.04em] text-ink-500">{roleLabel(user)}</span>
      <span className="text-sm font-medium leading-tight text-ink-900">{user.name}</span>
    </button>
  );
}

export interface QuickSignInProps {
  users: DemoUser[];
  /** Email currently being signed in, if any. */
  signingEmail: string | null;
  busy: boolean;
  onPick: (u: DemoUser) => void;
}

/** DEMO_MODE only: one-click accounts. Four most-used first, the rest behind a closed disclosure. */
export function QuickSignIn({ users, signingEmail, busy, onPick }: QuickSignInProps) {
  const { start, more } = splitUsers(users);
  const signing = users.find((u) => u.email === signingEmail);
  return (
    <section className="mt-7 border-t border-line pt-5" aria-labelledby="quick-h">
      <h2 id="quick-h" className="text-sm font-semibold text-ink-900">
        Quick sign-in for the demo
      </h2>
      <div className="label-caps mb-1.5 mt-3">Start here</div>
      <div className="grid grid-cols-2 gap-2">
        {start.map((u) => (
          <Pick key={u.email} user={u} disabled={busy} active={signingEmail === u.email} onPick={onPick} />
        ))}
      </div>

      {more.length > 0 && (
        <details className="group mt-3">
          <summary className="focus-ring inline-flex cursor-pointer list-none items-center gap-1 rounded text-sm text-navy hover:underline [&::-webkit-details-marker]:hidden">
            <ChevronRight {...ICON} size={14} className="transition-transform group-open:rotate-90" />
            More accounts ({more.length})
          </summary>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {more.map((u) => (
              <Pick key={u.email} user={u} disabled={busy} active={signingEmail === u.email} onPick={onPick} />
            ))}
          </div>
        </details>
      )}

      <div className="mt-3 min-h-[20px] text-xs text-ink-500" role="status" aria-live="polite">
        {signing ? `Signing in as ${signing.name}…` : (
          <>
            Password for all demo accounts: <span className="font-mono tnum text-ink-900">{DEMO_PASSWORD}</span>
          </>
        )}
      </div>
    </section>
  );
}
