import type { ReactNode } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import type { Role } from '@/lib/constants';
import { useAuth } from './AuthContext';
import { Skeleton } from '@/components/ui/Skeleton';

/** Redirects to /login (remembering where the officer was heading). */
export function RequireAuth({ children }: { children?: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading && !user) {
    return (
      <div className="p-6">
        <Skeleton width={240} height={20} />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  return <>{children ?? <Outlet />}</>;
}

/** Use as a layout route (<Route element={<RequireRole roles={[...]} />}>) or wrapping children. */
export function RequireRole({ roles, children }: { roles: Role[]; children?: ReactNode }) {
  const { user } = useAuth();
  if (!user) return null;
  if (!roles.includes(user.role)) {
    return (
      <div className="px-6 py-5">
        <h1 className="text-xl font-semibold">Not available for your role</h1>
        <p className="mt-2 text-sm text-ink-500">This screen is limited to other roles. Ask an administrator if you need access.</p>
      </div>
    );
  }
  return <>{children ?? <Outlet />}</>;
}
