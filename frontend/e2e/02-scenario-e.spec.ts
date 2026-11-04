import { test, expect } from '@playwright/test';
import { loginAs, settle, shot } from './helpers';

/** Scenario E in the UI: near-twin -> Needs review (both candidates) -> confirm one -> alias -> same text is EXACT. */
test('Scenario E: near-twin goes to review, confirm saves alias, re-entry is exact', async ({ page }) => {
  await loginAs(page, 'pgrc.officer');
  await page.goto('/cases/new');
  await page.getByRole('button', { name: 'Demo inputs' }).click();
  await page.getByRole('menuitem', { name: /Scenario E/ }).click();
  await page.getByRole('button', { name: 'Save case' }).click();

  await expect(page.getByText('Needs review').first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Two similar institutions in Lucknow/).first()).toBeVisible();
  await page.getByRole('button', { name: 'Change' }).click();
  const cand = page.getByText(/Top \d candidates/);
  await expect(cand).toBeVisible();
  await expect(page.getByText('Shri Ram College of Engineering, Lucknow').first()).toBeVisible();
  await expect(page.getByText('Shri Ram Institute of Technology, Lucknow').first()).toBeVisible();
  await settle(page);
  await shot(page, 'scenario-e-review');

  // confirm the pre-selected College candidate (officer decision)
  await page.getByRole('button', { name: 'Confirm', exact: true }).first().click();
  await expect(page.getByText(/Confirmed by you/)).toBeVisible();
  await expect(page.getByText(/Alias saved|alias/i).first()).toBeVisible();

  // same text again -> EXACT via alias
  await page.getByRole('button', { name: 'New case' }).first().click();
  await page.getByRole('button', { name: 'Demo inputs' }).click();
  await page.getByRole('menuitem', { name: /Scenario E/ }).click();
  await page.getByRole('button', { name: 'Save case' }).click();
  await expect(page.getByText(/Exact match via confirmed alias/)).toBeVisible({ timeout: 20_000 });
  await shot(page, 'scenario-e-exact');
});

test('review queue renders cards with candidates, Confirm this, None of these (keyboard shortcuts not exercised)', async ({ page }) => {
  await loginAs(page, 'pgrc.officer');
  await page.goto('/review');
  await expect(page.getByRole('heading', { name: /Review queue|Institution match review/i })).toBeVisible();
  await settle(page);
  await shot(page, 'review');
  await expect(page.getByRole('button', { name: /Confirm this/ }).first()).toBeVisible();
  await expect(page.getByText(/None of these/).first()).toBeVisible();
});
