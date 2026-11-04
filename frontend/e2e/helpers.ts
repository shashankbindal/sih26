import { expect, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));

export const API = process.env.QA_API_URL ?? 'http://localhost:8000/api/v1';
export const PASSWORD = 'Demo@2026';
export const SHOTS = path.resolve(HERE, '..', '..', 'docs', 'screenshots');

export type Who =
  | 'pgrc.officer' | 'pgrc.head' | 'rb.officer' | 'rb.head' | 'approval.officer' | 'vigilance.officer'
  | 'ro.kanpur' | 'ro.bhopal' | 'ro.chandigarh' | 'mgmt' | 'admin';

const cache = new Map<string, { token: string; user: unknown }>();

export async function apiLogin(who: Who) {
  if (cache.has(who)) return cache.get(who)!;
  const r = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: `${who}@demo.loksutra.in`, password: PASSWORD }),
  });
  if (!r.ok) throw new Error(`login ${who}: ${r.status}`);
  const j = (await r.json()) as { access_token: string; user: unknown };
  const v = { token: j.access_token, user: j.user };
  cache.set(who, v);
  return v;
}

/** API login + seed sessionStorage (token + user) before the app boots; avoids typing in the form. */
export async function loginAs(page: Page, who: Who) {
  const { token, user } = await apiLogin(who);
  await page.addInitScript(([t, u]) => {
    try {
      window.sessionStorage.setItem('loksutra.token', t as string);
      window.sessionStorage.setItem('loksutra.user', JSON.stringify(u));
    } catch { /* ignore */ }
  }, [token, user]);
}

export async function api<T = any>(who: Who, method: string, p: string, body?: unknown): Promise<T> {
  const { token } = await apiLogin(who);
  const r = await fetch(`${API}${p}`, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`${method} ${p} -> ${r.status} ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : (undefined as T);
}

export async function shot(page: Page, name: string, opts: { fullPage?: boolean } = {}) {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `qa-${name}.png`), fullPage: opts.fullPage ?? false });
}

/** Wait for the app to settle: no skeleton placeholders, network idle. */
export async function settle(page: Page) {
  await page.waitForLoadState('networkidle').catch(() => undefined);
  await page.waitForTimeout(400);
}

export async function institutionId(who: Who, permanentId: string): Promise<string> {
  const r = await api(who, 'GET', `/institutions?q=${encodeURIComponent(permanentId)}`);
  return r.items.find((i: any) => i.permanent_id === permanentId).id;
}

export { expect };
