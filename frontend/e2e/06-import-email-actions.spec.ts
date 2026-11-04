import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loginAs, settle, shot } from './helpers';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SAMPLE = path.resolve(HERE, '..', '..', 'backend', 'app', 'seed', 'data', 'sample_import.csv');

test('import stepper: upload sample CSV, map, preview, run, summary with counts', async ({ page }) => {
  await loginAs(page, 'pgrc.officer');
  await page.goto('/import');
  await page.getByLabel('Choose a CSV or XLSX file').setInputFiles(SAMPLE);
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByText(/Map columns|Field for column/i).first()).toBeVisible();
  await shot(page, 'import-map');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByText(/first 20 rows|Preview/i).first()).toBeVisible();
  await shot(page, 'import-preview');
  await page.getByRole('button', { name: 'Continue' }).click();
  const t0 = Date.now();
  await page.getByRole('button', { name: 'Run import' }).click();
  await expect(page.getByText(/imported/i).first()).toBeVisible({ timeout: 60_000 });
  const secs = (Date.now() - t0) / 1000;
  await settle(page);
  const body = await page.locator('body').innerText();
  expect(body).toMatch(/needs review/i);
  expect(body).toMatch(/unresolved/i);
  expect(body).toMatch(/links/i);
  console.log('UI IMPORT 200 rows seconds', secs);
  expect(secs).toBeLessThan(30);
  await shot(page, 'import-summary');
});

test('paste email: parser prefills the case form', async ({ page }) => {
  await loginAs(page, 'pgrc.officer');
  await page.goto('/cases/new');
  await page.getByRole('tab', { name: 'Paste email' }).click();
  const raw = [
    'From: Demo Parent <demo.parent@mailbox.example>',
    'Subject: Fee refund not received - Shrinath Institute of Engineering & Technology, Kanpur',
    '',
    'Respected Sir, my son withdrew admission at Shrinath Institute of Engineering & Technology, Kanpur (Permanent ID 1-4463974255).',
    'The college is not refunding Rs. 85,000. Earlier CPGRAMS ref DHIGH/E/2026/0099999 refers.',
  ].join('\n');
  await page.getByLabel(/Raw email text/).fill(raw);
  await page.getByRole('button', { name: 'Parse email' }).click();
  await expect(page.getByLabel('Permanent ID (optional)')).toHaveValue('1-4463974255');
  await expect(page.getByLabel(/^Subject/)).toHaveValue(/Fee refund not received/);
  await shot(page, 'new-case-from-email');
});

test('case actions: add remark and update status from the case page write Passport entries', async ({ page }) => {
  await loginAs(page, 'pgrc.officer');
  await page.goto('/cases?q=LS-2026-000455');
  await page.getByRole('row', { name: /LS-2026-000455/ }).first().click();
  await page.getByRole('link', { name: /Open case/ }).click();
  await expect(page.getByRole('heading', { name: 'LS-2026-000455' })).toBeVisible();
  await page.getByRole('button', { name: 'Add remark' }).click();
  await page.getByRole('dialog').getByRole('textbox').first().fill('E2E remark: reminder sent to the institution registrar.');
  await page.getByRole('dialog').getByRole('button', { name: /Add remark|Save|Submit/ }).last().click();
  await page.getByRole('tab', { name: /Case Passport/ }).click();
  await expect(page.getByText('E2E remark: reminder sent').first()).toBeVisible();
  await page.getByRole('button', { name: /Verify chain/ }).click();
  await expect(page.getByText(/Chain verified · \d+ entries/)).toBeVisible();
});
