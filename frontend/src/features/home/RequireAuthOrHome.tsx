import { Navigate, useLocation } from 'react-router-dom';
import { RequireAuth, useAuth } from '@/auth';

/** Guard for the app shell: signed-out visitors at "/" see the public Home page, everything else goes to the login as before. */
export function RequireAuthOrHome() {
  const { user, loading } = useAuth();
  const { pathname } = useLocation();
  if (!user && !loading && pathname === '/') return <Navigate to="/home" replace />;
  return <RequireAuth />;
}
