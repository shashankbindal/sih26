import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { api } from '@/api/client';
import { ICON } from '@/lib/icons';
import { cx } from '@/lib/cx';
import { formatDateTimeShort, formatTime, daysSince } from '@/lib/format';
import { NOTIFICATION_KIND_LABEL, type NotificationKind } from '@/lib/constants';
import { Popover } from '@/components/ui/Popover';
import { Tooltip } from '@/components/ui/Tooltip';
import { Badge } from '@/components/ui/Badge';

interface Notification {
  id: string;
  kind: NotificationKind;
  title: string;
  body?: string | null;
  link_path?: string | null;
  created_at: string;
  read_at?: string | null;
}

function unwrap(data: unknown): Notification[] {
  if (Array.isArray(data)) return data as Notification[];
  const d = data as { items?: Notification[] } | null;
  return d?.items ?? [];
}

const kindTone = (k: NotificationKind) =>
  k === 'PRIORITY_REVIEW' || k === 'SLA_BREACH' ? 'red' : k === 'SLA_AMBER' ? 'amber' : k === 'COORDINATION_REQUIRED' ? 'amber' : 'info';

/** Bell with unread count; dropdown grouped Today / Earlier; click goes to link_path. */
export function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const close = useCallback(() => setOpen(false), []);

  const q = useQuery<Notification[]>({
    queryKey: ['notifications'],
    queryFn: async ({ signal }) => unwrap(await api.get<unknown>('/notifications', { signal })),
    refetchInterval: 60_000,
    retry: false,
  });
  const items = q.data ?? [];
  const unread = items.filter((n) => !n.read_at);
  const today = items.filter((n) => daysSince(n.created_at) === 0);
  const earlier = items.filter((n) => daysSince(n.created_at) !== 0);

  const markRead = async (n: Notification) => {
    close();
    if (!n.read_at) {
      try {
        await api.post(`/notifications/${n.id}/read`);
        void qc.invalidateQueries({ queryKey: ['notifications'] });
      } catch {
        /* navigation still proceeds */
      }
    }
    if (n.link_path) navigate(n.link_path);
  };
  const readAll = async () => {
    try {
      await api.post('/notifications/read-all');
      void qc.invalidateQueries({ queryKey: ['notifications'] });
    } catch {
      /* ignore */
    }
  };

  const group = (label: string, list: Notification[]) =>
    list.length > 0 && (
      <div>
        <div className="label-caps border-y border-line-soft bg-paper px-3 py-1">{label}</div>
        {list.map((n) => (
          <button key={n.id} type="button" onClick={() => markRead(n)} className={cx('focus-ring block w-full border-b border-line-soft px-3 py-2 text-left hover:bg-navy-50', !n.read_at && 'bg-surface')}>
            <div className="flex items-center justify-between gap-2">
              <Badge tone={kindTone(n.kind)}>{NOTIFICATION_KIND_LABEL[n.kind] ?? n.kind}</Badge>
              <span className="tnum text-xs text-ink-500">{daysSince(n.created_at) === 0 ? formatTime(n.created_at) : formatDateTimeShort(n.created_at)}</span>
            </div>
            <div className={cx('mt-1 text-sm', n.read_at ? 'text-ink-500' : 'font-medium text-ink-900')}>{n.title}</div>
          </button>
        ))}
      </div>
    );

  return (
    <Popover
      open={open}
      onClose={close}
      align="right"
      label="Notifications"
      panelClassName="w-[380px]"
      trigger={
        <Tooltip content="Notifications">
          <button
            type="button"
            aria-label={`Notifications, ${unread.length} unread`}
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
            className="focus-ring relative inline-flex h-ctl w-9 items-center justify-center rounded border border-transparent text-ink-700 hover:bg-paper"
          >
            <Bell {...ICON} />
            {unread.length > 0 && (
              <span className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-sm bg-red px-1 font-mono text-2xs text-surface tnum">
                {unread.length > 99 ? '99+' : unread.length}
              </span>
            )}
          </button>
        </Tooltip>
      }
    >
      <div className="flex h-10 items-center justify-between border-b border-line px-3">
        <span className="text-sm font-semibold">Notifications</span>
        {unread.length > 0 && (
          <button type="button" onClick={readAll} className="focus-ring text-xs text-navy hover:underline" style={{ background: 'none', border: 0 }}>
            Mark all read
          </button>
        )}
      </div>
      <div className="max-h-[400px] overflow-y-auto">
        {q.isLoading && <div className="px-3 py-3 text-sm text-ink-500">Loading{'…'}</div>}
        {!q.isLoading && items.length === 0 && <div className="px-3 py-3 text-sm text-ink-500">{q.isError ? 'Notifications are unavailable right now.' : 'No notifications.'}</div>}
        {group('Today', today)}
        {group('Earlier', earlier)}
      </div>
    </Popover>
  );
}
