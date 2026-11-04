import { test, expect, type Page } from '@playwright/test';
import { api, institutionId, loginAs, settle, shot, type Who } from './helpers';

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const ENUM = /\b[A-Z]{3,}_[A-Z_]{2,}\b/;

function collectConsole(page: Page) {
  const msgs: string[] = [];
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) msgs.push(m.text()); });
  page.on('pageerror', (e) => msgs.push('pageerror ' + e.message));
  return msgs;
}

test('D3: Scenario C link compare shows the hold-letters action and lead bureau RB', async ({ page }) => {
  const dev = await institutionId('admin', '1-4471203398');
  const links = await api('admin', 'GET', `/institutions/${dev}/links`);
  const conf = links.find((l: any) => l.relation === 'CONFLICTING');
  await loginAs(page, 'rb.head');
  await page.goto(`/coordination/${conf.id}`);
  await expect(page.getByText('Priority review').first()).toBeVisible();
  await expect(page.getByText(/Hold issue of further letters until bureau heads agree/).first()).toBeVisible();
  const body = await page.locator('body').innerText();
  expect(body).not.toMatch(/No shared action suggested/);
  const lead = body.slice(body.indexOf('Lead bureau suggestion'), body.indexOf('Lead bureau suggestion') + 80);
  expect(lead).toMatch(/\bRB\b/);
  await settle(page);
  await page.getByText('Suggested shared next action').scrollIntoViewIfNeeded();
  await shot(page, 'v-link-compare-scenario-c');
});

test('V1/V2: attention cells at 1366 are not clipped and their numbers share one baseline', async ({ page }) => {
  await loginAs(page, 'mgmt');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Oversight dashboard' })).toBeVisible();
  await settle(page);
  const r = await page.evaluate(() => {
    const labels = ['Past deadline', 'Priority review', 'Coordination needed'];
    const out: any[] = [];
    const all = Array.from(document.querySelectorAll<HTMLElement>('body *'));
    for (const l of labels) {
      const el = all.filter((e) => (e.textContent ?? '').trim() === l && e.getBoundingClientRect().top > 150 && e.getBoundingClientRect().top < 420).sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length)[0];
      if (!el) { out.push({ l, missing: true }); continue; }
      let node: HTMLElement | null = el.parentElement;
      let num: HTMLElement | null = null;
      for (let i = 0; i < 4 && node && !num; i++, node = node.parentElement) {
        num = Array.from(node.querySelectorAll<HTMLElement>('*')).find((e) => e.children.length === 0 && parseFloat(getComputedStyle(e).fontSize) >= 26) ?? null;
      }
      const lr = el.getBoundingClientRect();
      const fs = parseFloat(getComputedStyle(el).fontSize);
      out.push({ l, labelLines: Math.round(lr.height / (fs * 1.3)), labelClipped: el.scrollWidth > el.clientWidth + 1, numTop: num ? Math.round(num.getBoundingClientRect().top) : null, right: Math.round(lr.right), vw: window.innerWidth });
    }
    return out;
  });
  console.log('ATTENTION', JSON.stringify(r));
  expect(r.filter((x) => x.missing), JSON.stringify(r.filter((x) => x.missing))).toEqual([]);
  expect(r.length).toBe(3);
  for (const x of r) {
    expect(x.labelClipped, x.l).toBeFalsy();
    expect(x.labelLines, `${x.l} label wraps to ${x.labelLines} lines`).toBeLessThanOrEqual(2);
    expect(x.right, x.l).toBeLessThanOrEqual(x.vw);
  }
  const tops = new Set(r.map((x) => x.numTop));
  expect(tops.size, `attention numbers not on one baseline: ${[...tops]}`).toBe(1);
  await shot(page, 'v-kpi-strip-1366');
});

test('Dashboard alerts table count equals the KPI count (All time)', async ({ page }) => {
  await loginAs(page, 'mgmt');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Oversight dashboard' })).toBeVisible();
  // The attention cells "Priority review" + "Coordination needed" together are the open alerts; the tab lists the same links.
  const attentionTotal = async () => {
    const num = async (label: string) => {
      const cell = page.getByRole('link', { name: new RegExp(label) }).first();
      return Number((await cell.innerText()).replace(/,/g, '').match(/\d+/)![0]);
    };
    return (await num('Priority review')) + (await num('Coordination needed'));
  };
  for (const range of ['All time', 'Last 90 days']) {
    await page.getByLabel(/Date range/i).selectOption({ label: range });
    await settle(page);
    const kpi = await attentionTotal();
    await page.getByRole('tab', { name: /Coordination alerts/ }).click();
    await settle(page);
    const body = await page.locator('body').innerText();
    const tbl = body.match(/(\d[\d,]*) open alerts?/);
    const tab = Number((await page.getByRole('tab', { name: /Coordination alerts/ }).innerText()).match(/\d+/)![0]);
    console.log(range, 'attention', kpi, 'table total', tbl?.[1], 'tab count', tab);
    expect(tbl, 'alerts footer text not found').toBeTruthy();
    expect(Number(tbl![1].replace(/,/g, '')), `${range}: alerts table vs attention cells`).toBe(kpi);
    expect(tab, `${range}: tab count vs attention cells`).toBe(kpi);
    await page.getByRole('tab', { name: 'Overview' }).click();
  }
});

test('V4: Institution 360 at 1366 and 1920, no overflow, swimlanes visible', async ({ page }) => {
  const sid = await institutionId('admin', '1-4463974255');
  await loginAs(page, 'pgrc.officer');
  for (const [w, h] of [[1366, 768], [1920, 1080]] as const) {
    await page.setViewportSize({ width: w, height: h });
    await page.goto(`/institutions/${sid}`);
    await expect(page.getByText('Open matters by bureau')).toBeVisible();
    await settle(page);
    const ov = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(ov).toBeLessThanOrEqual(0);
    await shot(page, `v-institution-360-${w}`);
    await page.getByText('Open matters by bureau').scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollBy(0, 250));
    await shot(page, `v-institution-360-${w}-scrolled`);
  }
});

test('V6: Passport text has no UUIDs or raw enum names', async ({ page }) => {
  const shr = await institutionId('admin', '1-4463974255');
  const tl = await api('admin', 'GET', `/institutions/${shr}/timeline`);
  const items = tl.items ?? tl;
  const c = items.find((x: any) => x.owner_bureau === 'PGRC' && x.relations?.length);
  await loginAs(page, 'pgrc.officer');
  await page.goto(`/cases/${c.id}`);
  await page.getByRole('tab', { name: /Case Passport/ }).click();
  await settle(page);
  await expect(page.getByText(/Chain not yet verified|Chain verified/).first()).toBeVisible();
  const txt = await page.locator('[role="tabpanel"], main').first().innerText();
  const m = txt.match(UUID);
  const e = txt.match(ENUM);
  expect(m, `UUID shown in Passport: ${m?.[0]}`).toBeNull();
  expect(e, `raw enum shown in Passport: ${e?.[0]}`).toBeNull();
  await shot(page, 'v-passport-humanised');
});

for (const who of ['pgrc.officer', 'pgrc.head', 'rb.head', 'approval.officer'] as Who[]) {
  test(`V7: nav badges equal tab counts for ${who}`, async ({ page }) => {
    const msgs = collectConsole(page);
    await loginAs(page, who);
    const badge = async (label: string) => {
      const t = await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: new RegExp(label) }).innerText();
      const m = t.match(/(\d+)\s*$/);
      return m ? Number(m[1]) : 0;
    };
    await page.goto('/coordination');
    await settle(page);
    const tabNeeds = Number(((await page.getByRole('tab', { name: /Needs my decision/ }).innerText()).match(/(\d+)/) ?? [])[1] ?? 0);
    expect(await badge('Coordination')).toBe(tabNeeds);
    await page.goto('/clearances');
    await settle(page);
    const pend = Number(((await page.getByRole('tab', { name: /Pending/ }).innerText()).match(/(\d+)/) ?? [])[1] ?? 0);
    expect(await badge('Clearances')).toBe(pend);
    await page.goto('/review');
    await settle(page);
    const rv = await page.getByText(/awaiting review/).first().innerText();
    expect(await badge('Review queue')).toBe(Number(rv.match(/(\d+)/)![1]));
    console.log(who, 'badges ok', tabNeeds, pend, rv);
    expect(msgs.filter((m) => /Query data cannot be undefined/.test(m))).toEqual([]);
  });
}

test("console has no 'Query data cannot be undefined' on main screens", async ({ page }) => {
  const msgs = collectConsole(page);
  await loginAs(page, 'pgrc.officer');
  const shr = await institutionId('admin', '1-4463974255');
  for (const r of ['/', '/cases', '/institutions', `/institutions/${shr}`, '/coordination', '/clearances', '/review', '/evaluation', '/reports']) {
    await page.goto(r);
    await settle(page);
  }
  const bad = msgs.filter((m) => !/React Router Future Flag/.test(m)).filter((m) => /cannot be undefined|Warning:|Uncaught|TypeError|Failed prop|pageerror/.test(m));
  expect(bad, bad.join(' | ')).toEqual([]);
});

test('D2 UI: Kanpur RO register defaults to own region; widening is possible; counts match API', async ({ page }) => {
  await loginAs(page, 'ro.kanpur');
  await page.goto('/cases');
  await settle(page);
  const body = await page.locator('body').innerText();
  const n = Number(body.match(/([\d,]+) cases/)![1].replace(/,/g, ''));
  const mine = await api('ro.kanpur', 'GET', '/cases?page_size=1');
  const all = await api('ro.kanpur', 'GET', '/cases?page_size=1&scope=all');
  console.log('RO register', n, 'api default', mine.total, 'scope=all', all.total);
  expect(n).toBe(mine.total);
  expect(mine.total).toBeLessThan(all.total);
  await shot(page, 'v-ro-cases-default-region');
});
