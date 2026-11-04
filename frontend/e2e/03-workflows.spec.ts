import { test, expect } from '@playwright/test';
import { api, institutionId, loginAs, settle, shot } from './helpers';

const uniq = () => Math.random().toString(16).slice(2, 8);

test('PGRC responds to a clearance request and the Approval officer sees the update', async ({ page, browser }) => {
  const sid = await institutionId('admin', '1-4463974255');
  const panel = await api('approval.officer', 'POST', `/institutions/${sid}/pre-action-check`, { action_type: 'SECURITY_DEPOSIT_RELEASE' });
  const aid = panel.institution_action_id as string;
  await api('approval.officer', 'POST', `/institution-actions/${aid}/clearances`, { target_bureau: 'PGRC', remark: 'E2E clearance request' });

  // PGRC inbox
  await loginAs(page, 'pgrc.officer');
  await page.goto('/clearances');
  await expect(page.getByRole('heading', { name: /Clearance inbox/i })).toBeVisible();
  const row = page.getByRole('row', { name: /Shrinath/ }).first();
  await expect(row).toBeVisible();
  await settle(page);
  await shot(page, 'clearances');
  await row.click();
  await page.getByLabel('Response').selectOption('CLEARED_WITH_REMARKS');
  await page.getByLabel(/Remarks/).fill('E2E: cleared, student dues to be tracked');
  await shot(page, 'clearance-respond');
  await page.getByRole('button', { name: /Send response|Submit|Respond/ }).click();
  await expect(page.getByText(/Response recorded|recorded|sent/i).first()).toBeVisible();

  // Approval sees the live update on the action page
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const ap = await ctx.newPage();
  await loginAs(ap, 'approval.officer');
  await ap.goto(`/institutions/${sid}/pre-action/${aid}`);
  await expect(ap.getByText(/Cleared with remarks/i).first()).toBeVisible({ timeout: 20_000 });
  await ctx.close();
});

test('RB officer sees a PGRC case with the complainant masked', async ({ page }) => {
  const name = `Zed Maskcheck${uniq()}`;
  const sid = await institutionId('admin', '1-4463974255');
  const created = await api('pgrc.officer', 'POST', '/cases', {
    source_channel: 'CSS', source_ref: `E2E-${uniq()}`, institution_text_raw: 'Shrinath Institute of Engineering and Technology Kanpur',
    permanent_id_raw: '1-4463974255', complainant: { name, email: `${uniq()}@mailbox.example`, phone: '9000012345', party_type: 'STUDENT' },
    subject: 'E2E privacy probe', description: 'E2E private description text that other bureaus must not read.', owner_bureau: 'PGRC',
  });
  expect(sid).toBeTruthy();
  await loginAs(page, 'rb.officer');
  await page.goto(`/cases/${created.case.id}`);
  await expect(page.getByText(created.case.display_id).first()).toBeVisible();
  await settle(page);
  const body = await page.locator('body').innerText();
  expect(body).not.toContain(name);
  expect(body).not.toContain('E2E private description text');
  expect(body).toMatch(/hidden/i);
  await expect(page.getByText(/Request access/i).first()).toBeVisible();
  await shot(page, 'case-masked');
  // The 'Normalised text' toggle must not reveal the masked description either
  const toggle = page.getByRole('button', { name: 'Normalised text' });
  if (await toggle.count()) {
    await toggle.click();
    await page.waitForTimeout(300);
    const after = await page.locator('body').innerText();
    expect(after, 'Normalised text toggle exposes the masked description').not.toMatch(/e2e private description text/i);
  }
  // the reason modal enforces >= 10 chars
  await page.getByText(/Request access/i).first().click();
  const reason = page.getByLabel(/Reason/i);
  await reason.fill('too short');
  await expect(page.getByRole('button', { name: /Reveal|Request|Submit|Confirm/ }).last()).toBeDisabled();
});

test('RO officer is scoped to own region on the dashboard and case register', async ({ page }) => {
  await loginAs(page, 'ro.kanpur');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Oversight dashboard' })).toBeVisible();
  await settle(page);
  await expect(page.getByText(/Region/i).first()).toBeVisible();
  const kpi = await api('ro.kanpur', 'GET', '/dashboard/kpis?from=2000-01-01');
  const all = await api('admin', 'GET', '/dashboard/kpis?from=2000-01-01');
  expect(kpi.total).toBeLessThan(all.total);
  await page.goto('/cases');
  await settle(page);
  const pager = await page.getByText(/of [\d,]+/).first().innerText();
  const n = Number(pager.match(/of ([\d,]+)/)![1].replace(/,/g, ''));
  const caseTotal = await api('admin', 'GET', '/cases?page_size=1');
  // Defect probe: the register should default to the RO's region
  expect(n, `RO register shows ${n} of ${caseTotal.total} cases`).toBeLessThan(caseTotal.total);
  await shot(page, 'ro-cases');
});

test('SENIOR_MGMT: Overdue KPI lands on a filtered case list with the same count; PDF downloads', async ({ page }) => {
  await loginAs(page, 'mgmt');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Oversight dashboard' })).toBeVisible();
  await settle(page);
  const cell = page.getByRole('link', { name: /Past deadline/ }).first();
  await expect(cell).toBeVisible();
  const kpiText = (await cell.innerText()).replace(/,/g, '');
  const kpi = Number(kpiText.match(/\n?(\d+)/g)!.map((x) => x.trim())[0]);
  await cell.click();
  await expect(page).toHaveURL(/\/cases\?/);
  await settle(page);
  const pager = await page.getByText(/of [\d,]+/).first().innerText();
  const n = Number(pager.match(/of ([\d,]+)/)![1].replace(/,/g, ''));
  expect(n).toBe(kpi);
  await shot(page, 'cases-overdue-from-kpi');

  await page.goto('/reports');
  await expect(page.getByRole('heading', { name: /Reports/i }).first()).toBeVisible();
  await settle(page);
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download PDF' }).click()]);
  const path = await dl.path();
  const fs = await import('node:fs');
  const buf = fs.readFileSync(path!);
  expect(buf.subarray(0, 5).toString()).toBe('%PDF-');
  expect(dl.suggestedFilename()).toMatch(/\.pdf$/i);
  const [dl2] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download CSV' }).click()]);
  expect(dl2.suggestedFilename()).toMatch(/\.csv$/i);
});

test('Admin tamper demo then Verify chain flags the exact entry', async ({ page }) => {
  const created = await api('pgrc.officer', 'POST', '/cases', {
    source_channel: 'CSS', source_ref: `E2E-T-${uniq()}`, institution_text_raw: 'Shrinath Engg College Kanpur', complainant: { name: 'E2E Tamper', party_type: 'STUDENT' },
    subject: 'E2E tamper probe', description: 'Fee refund not received after withdrawal.', owner_bureau: 'PGRC',
  });
  await api('pgrc.officer', 'POST', `/cases/${created.case.id}/remarks`, { remark: 'E2E remark' });
  await loginAs(page, 'admin');
  await page.goto('/admin');
  await page.getByRole('tab', { name: /Demo tools/ }).click();
  await page.getByLabel('Case ID').fill(created.case.display_id);
  await page.getByRole('button', { name: 'Tamper', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: /Tamper|Confirm|Alter/ }).last().click();
  await expect(page.getByText(/seq \d+|entry \d+|Entry \d+/i).first()).toBeVisible();
  await shot(page, 'admin-tamper');
  await page.goto(`/cases/${created.case.id}`);
  await page.getByRole('tab', { name: /Case Passport|Passport/ }).click();
  await page.getByRole('button', { name: /Verify chain/ }).click();
  const bad = page.getByText(/broken|Chain broken|first broken|Tampered|failed/i).first();
  await expect(bad).toBeVisible();
  const txt = await bad.innerText();
  const seqShown = Number((txt.match(/(?:entry|seq|#)\s*(\d+)/i) ?? [])[1]);
  const v = await api('admin', 'GET', `/cases/${created.case.id}/passport/verify`);
  expect(v.ok).toBe(false);
  expect(seqShown, `UI text: ${txt}`).toBe(v.first_bad_seq);
  await shot(page, 'passport-broken');
});
