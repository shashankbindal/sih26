import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, errorMessage } from '@/api/client';
import { useAuth } from '@/auth';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { ColdStartBanner } from '@/components/domain/ColdStartBanner';
import { DEMO_MODE } from '@/lib/env';
import { EnvBar } from '@/shell/EnvBar';
import { Wordmark } from '@/shell/Wordmark';
import { DEMO_PASSWORD, FALLBACK_USERS, unwrapUsers, type DemoUser } from './demoUsers';
import { LoginAside } from './LoginAside';
import { QuickSignIn } from './QuickSignIn';

/** Login: two full-height panels (navy story panel + sign-in block); stacks with the form first at <= 900px. */
export function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from ?? '/';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [signingEmail, setSigningEmail] = useState<string | null>(null);

  const demo = useQuery<DemoUser[]>({
    queryKey: ['demo-users'],
    queryFn: async () => unwrapUsers(await api.get<unknown>('/auth/demo-users', { anonymous: true })),
    enabled: DEMO_MODE,
    retry: false,
    staleTime: Infinity,
  });
  // API list is the source of truth; the built-in copy is only a fallback when it is unreachable.
  const users = demo.data && demo.data.length > 0 ? demo.data : FALLBACK_USERS;

  if (user) return <Navigate to={from} replace />;

  const run = async (mail: string, pass: string) => {
    setError(null);
    setBusy(true);
    try {
      await login(mail.trim(), pass);
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
      setSigningEmail(null);
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSigningEmail(null);
    void run(email, password);
  };

  const quick = (u: DemoUser) => {
    setEmail(u.email);
    setPassword(DEMO_PASSWORD);
    setSigningEmail(u.email);
    void run(u.email, DEMO_PASSWORD);
  };

  return (
    <div className="flex h-full flex-col">
      <EnvBar />
      <ColdStartBanner />
      <div className="flex min-h-0 flex-1 max-[900px]:flex-col max-[900px]:overflow-y-auto">
        <main className="flex min-w-0 flex-1 overflow-y-auto bg-surface px-6 py-8 max-[900px]:overflow-visible min-[901px]:px-10">
          <div className="m-auto w-full max-w-[440px]">
            <div className="mb-6 min-[901px]:hidden">
              <Wordmark tone="light" />
            </div>
            <h1 className="text-xl font-semibold">Sign in</h1>
            <form onSubmit={submit} className="mt-4 flex flex-col gap-4" noValidate>
              <Field label="Email" required>
                <Input
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoFocus
                  className="!h-10"
                />
              </Field>
              <Field label="Password" required>
                <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="!h-10" />
              </Field>
              {error && (
                <div role="alert" className="rounded border border-red bg-red-bg px-3 py-2 text-sm text-red">
                  {error}
                </div>
              )}
              <Button type="submit" variant="primary" loading={busy} disabled={!email || !password} className="!h-10 w-full">
                Sign in
              </Button>
            </form>

            {DEMO_MODE && <QuickSignIn users={users} signingEmail={signingEmail} busy={busy} onPick={quick} />}
          </div>
        </main>
        <LoginAside />
      </div>
    </div>
  );
}
