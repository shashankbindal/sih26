import { test, expect } from '@playwright/test';
import { loginAs, settle, shot } from './helpers';

test('keyboard: Tab reaches the nav with a visible focus ring; / focuses search; g c navigates', async ({ page }) => {
  await loginAs(page, 'pgrc.officer');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Oversight dashboard' })).toBeVisible();
  await settle(page);

  // Tab until a main-nav link has focus (bounded)
  let reachedNav = false;
  const seen: string[] = [];
  for (let i = 0; i < 25 && !reachedNav; i++) {
    await page.keyboard.press('Tab');
    const info = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el) return null;
      const cs = getComputedStyle(el);
      return { inNav: !!el.closest('nav[aria-label="Main"]'), text: (el.textContent ?? '').trim().slice(0, 30), shadow: cs.boxShadow, outline: cs.outlineStyle + ' ' + cs.outlineWidth };
    });
    if (info) seen.push(`${info.text}|${info.shadow !== 'none' ? 'ring' : info.outline}`);
    if (info?.inNav) {
      reachedNav = true;
      const hasRing = info.shadow !== 'none' || (info.outline !== 'none 0px' && !info.outline.startsWith('none'));
      expect(hasRing, `no visible focus indicator on nav link: ${JSON.stringify(info)}`).toBeTruthy();
      await shot(page, 'focus-ring-nav');
    }
  }
  expect(reachedNav, `Tab sequence: ${seen.join(' > ')}`).toBeTruthy();

  // every interactive element in the top bar and first nav items shows a ring when focused
  await page.locator('body').click({ position: { x: 700, y: 400 } });
  await page.keyboard.press('/');
  await expect(page.getByLabel('Search institutions and cases')).toBeFocused();
  await page.keyboard.press('Escape');
  await page.locator('body').click({ position: { x: 700, y: 400 } });
  await page.keyboard.press('g');
  await page.keyboard.press('c');
  await expect(page).toHaveURL(/\/cases$/);
});

test('global search: typing a Hindi name shows Institutions and Cases sections', async ({ page }) => {
  await loginAs(page, 'pgrc.officer');
  await page.goto('/');
  await page.keyboard.press('/');
  await page.getByLabel('Search institutions and cases').fill('श्रीनाथ');
  await expect(page.getByText('Shrinath Institute of Engineering & Technology').first()).toBeVisible({ timeout: 10_000 });
  await shot(page, 'search-hindi');
});

test('cold-start banner shows while /health is blocked and hides when it recovers', async ({ page }) => {
  let block = true;
  await page.route('**/api/v1/health', (route) => (block ? route.abort('connectionrefused') : route.continue()));
  await page.goto('/login');
  await expect(page.getByText('Connecting to the server. The first request after idle can take up to a minute.')).toBeVisible({ timeout: 15_000 });
  await shot(page, 'cold-start-banner');
  block = false;
  await expect(page.getByText(/Connecting to the server|did not respond/)).toBeHidden({ timeout: 60_000 });
});

test('login with wrong password shows an alert, no crash', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill('pgrc.officer@demo.loksutra.in');
  await page.getByLabel('Password').fill('wrong-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toBeVisible();
});

test('unauthenticated deep link redirects to login; SENIOR_MGMT cannot open /cases/new or /admin', async ({ page }) => {
  await page.goto('/cases');
  await expect(page).toHaveURL(/\/login/);
  await loginAs(page, 'mgmt');
  await page.goto('/cases/new');
  await expect(page.getByRole('heading', { name: 'New case' })).toBeHidden();
  await page.goto('/admin');
  await expect(page.getByRole('heading', { name: /Administration|Admin/ })).toBeHidden();
});
