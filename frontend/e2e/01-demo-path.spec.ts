import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import { api, institutionId, loginAs, settle, shot, SHOTS } from './helpers';

/** Demo path: login -> New case (Scenario A) -> resolution + links -> Institution 360 -> Pre-Action Check
 *  -> clearance request -> Passport verify -> Dashboard. Scripted interaction is timed (target < 90 s). */
test('demo path runs end to end in under 90 s of scripted interaction', async ({ page, browser }) => {
  const t0 = Date.now();
  const marks: Record<string, number> = {};
  const mark = (k: string) => (marks[k] = Math.round((Date.now() - t0) / 100) / 10);
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|tile\.openstreetmap|ERR_BLOCKED|Failed to load resource/.test(m.text())) errors.push(m.text()); });

  // 1. real UI login (PGRC officer): one click on the quick sign-in button signs in
  await page.goto('/login');
  await shot(page, 'login');
  await page.getByRole('button', { name: /Ritu Sharma/ }).click();
  await expect(page.getByRole('heading', { name: 'Oversight dashboard' })).toBeVisible();
  mark('login');

  // 2. New case, Demo inputs -> Scenario A -> Save
  await page.getByRole('link', { name: 'New case' }).click();
  await expect(page.getByRole('heading', { name: 'New case' })).toBeVisible();
  await page.getByRole('button', { name: 'Demo inputs' }).click();
  await page.getByRole('menuitem', { name: /Scenario A/ }).click();
  await page.getByRole('button', { name: 'Save case' }).click();

  // 3. resolution + links
  await expect(page.getByText('Shrinath Institute of Engineering & Technology').first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Auto-suggested/i).first()).toBeVisible();
  await expect(page.getByText(/Coordination required/i).first()).toBeVisible();
  await expect(page.getByText(/transliteration/i).first()).toBeVisible();
  await settle(page);
  await shot(page, 'new-case-result');
  mark('new-case-result');

  // 4. Institution 360 (via the institution card link)
  await page.getByRole('link', { name: /Shrinath Institute of Engineering/ }).first().click();
  await expect(page.getByRole('heading', { name: /Shrinath Institute of Engineering/ })).toBeVisible();
  await expect(page.getByText('1-4463974255').first()).toBeVisible();
  await settle(page);
  mark('institution-360');

  // 5-7. Approval officer: Actions -> Security-deposit release -> Pre-Action Check -> request PGRC clearance -> hold
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const ap = await ctx.newPage();
  await loginAs(ap, 'approval.officer');
  const sid = await institutionId('admin', '1-4463974255');
  await ap.goto(`/institutions/${sid}`);
  await ap.getByRole('button', { name: /Actions/ }).click();
  await ap.getByRole('menuitem', { name: /Security-deposit release/ }).click();
  await expect(ap.getByText(/Advisory only/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(ap.getByText('APH 2024-27 · Security-deposit release procedure').first()).toBeVisible();
  await expect(ap.getByText(/Inst\. 7-day · overdue 4 days/).first()).toBeVisible();
  await settle(ap);
  await shot(ap, 'pre-action');
  mark('pre-action');
  await ap.getByRole('button', { name: /Request PGRC clearance/ }).click();
  await expect(ap.getByText(/Requested/i).first()).toBeVisible();
  await ap.getByRole('checkbox', { name: /I have seen/ }).check();
  await ap.getByRole('button', { name: 'Put on hold' }).click();
  await expect(ap.getByText(/On hold|Placed on hold|hold/i).first()).toBeVisible();
  mark('clearance+hold');

  // Passport verify on the action chain
  await ap.getByRole('button', { name: /Verify chain/ }).click();
  await expect(ap.getByText(/Chain verified · \d+ entries/)).toBeVisible();
  mark('passport-verify');
  await shot(ap, 'passport-verified');

  // 8. Dashboard
  await ap.getByRole('link', { name: 'Dashboard' }).click();
  await expect(ap.getByRole('heading', { name: 'Oversight dashboard' })).toBeVisible();
  await expect(ap.getByText('Coordination needed').first()).toBeVisible();
  await settle(ap);
  mark('dashboard');

  const secs = (Date.now() - t0) / 1000;
  fs.mkdirSync(SHOTS, { recursive: true });
  fs.writeFileSync(`${SHOTS}/../qa-demo-path-timing.json`, JSON.stringify({ total_seconds: secs, marks, errors }, null, 1));
  console.log('DEMO PATH SECONDS', secs, JSON.stringify(marks));
  expect(errors, `console/page errors: ${errors.join(' | ')}`).toEqual([]);
  expect(secs).toBeLessThan(90);
  await api('admin', 'GET', '/auth/me');
  await ctx.close();
});
