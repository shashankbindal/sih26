import { Outlet } from 'react-router-dom';
import { ColdStartBanner } from '@/components/domain/ColdStartBanner';
import { EnvBar } from './EnvBar';
import { SideNav } from './SideNav';
import { GlobalSearch } from './GlobalSearch';
import { NotificationsMenu } from './NotificationsMenu';
import { UserMenu } from './UserMenu';
import { useGlobalShortcuts } from './useShortcuts';

/** Environment bar, left nav 232px, top bar 52px, scrolling content, prototype footer note. */
export function AppLayout() {
  useGlobalShortcuts();
  return (
    <div className="flex h-full flex-col">
      <EnvBar />
      <div className="flex min-h-0 flex-1">
        <SideNav />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-topbar shrink-0 items-center justify-between gap-4 border-b border-line bg-surface px-6">
            <GlobalSearch />
            <div className="flex items-center gap-2">
              <NotificationsMenu />
              <span aria-hidden className="mx-1 h-6 w-px bg-line" />
              <UserMenu />
            </div>
          </header>
          <ColdStartBanner />
          <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
            <div className="flex-1 px-6 py-5">
              <Outlet />
            </div>
            <footer className="border-t border-line px-6 py-2 text-2xs text-ink-500">
              Prototype {'·'} synthetic data modelled on AICTE Permanent ID format
            </footer>
          </main>
        </div>
      </div>
    </div>
  );
}
