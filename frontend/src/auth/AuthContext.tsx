import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, ApiError, setUnauthorizedHandler } from '@/api/client';
import { getToken, setToken } from '@/api/token';
import type { Bureau, Role } from '@/lib/constants';

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: Role;
  bureau: Bureau;
  /** Regional office code for RO users, e.g. KNP. */
  ro_code?: string | null;
  designation?: string | null;
}

interface LoginResponse {
  access_token: string;
  user: AuthUser;
}

interface AuthState {
  user: AuthUser | null;
  /** True while a stored token is being re-validated on first load. */
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => void;
}

const USER_KEY = 'loksutra.user';
const Ctx = createContext<AuthState | null>(null);

function readStoredUser(): AuthUser | null {
  if (!getToken()) return null;
  try {
    const raw = window.sessionStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}
function storeUser(u: AuthUser | null) {
  try {
    if (u) window.sessionStorage.setItem(USER_KEY, JSON.stringify(u));
    else window.sessionStorage.removeItem(USER_KEY);
  } catch {
    /* in-memory only */
  }
}

/** JWT in memory + sessionStorage. A 401 from any request signs the user out. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [user, setUser] = useState<AuthUser | null>(readStoredUser);
  const [loading, setLoading] = useState<boolean>(() => !!getToken());

  const logout = useCallback(() => {
    setToken(null);
    storeUser(null);
    setUser(null);
    qc.clear();
  }, [qc]);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  // Re-validate a restored session once. Network errors keep the stored user (cold start).
  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    let live = true;
    api
      .get<AuthUser>('/auth/me')
      .then((u) => {
        if (!live) return;
        storeUser(u);
        setUser(u);
      })
      .catch((e: unknown) => {
        if (!live) return;
        if (e instanceof ApiError && e.status === 401) logout();
      })
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<LoginResponse>('/auth/login', { email, password }, { anonymous: true });
    setToken(res.access_token);
    storeUser(res.user);
    setUser(res.user);
    return res.user;
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth must be used inside AuthProvider');
  return v;
}
