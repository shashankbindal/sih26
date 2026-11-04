import { expect, test } from '@playwright/test';

test.describe('public Home page', () => {
  test('renders the short explanatory page without signing in', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (m) => {
      if (m.type() === 'error' && !/Failed to load resource|net::ERR/.test(m.text())) errors.push(m.text());
    });
    page.on('pageerror', (e) => errors.push(String(e)));

    await page.goto('/home');
    await expect(page.getByRole('heading', { level: 1, name: 'One institution. One truth.' })).toBeVisible();
    for (const id of ['top', 'problem', 'flow', 'architecture', 'matrix']) {
      await expect(page.locator(`#${id}`)).toBeVisible();
    }
    await expect(page.getByRole('contentinfo')).toContainText('SIH26264');
    await expect(page.locator('#problem li')).toHaveCount(3);
    await expect(page.locator('#flow li')).toHaveCount(4);
    // architecture diagram has a text alternative (the row version is the visible one on desktop)
    await expect(page.locator('svg[role="img"] title#arch-title')).toHaveCount(1);
    await expect(page.getByRole('group', { name: 'Impact and feasibility matrix' })).toBeVisible();
    await expect(page.getByText('Start here')).toBeVisible();
    // "See how it works" scrolls to the flow
    await page.getByRole('link', { name: 'See how it works' }).click();
    await expect(page).toHaveURL(/#flow$/);
    // plain-word guide: collapsed first, opens on click, 13 rows
    const words = page.locator('#words details');
    await expect(words).toHaveCount(1);
    await expect(words).not.toHaveAttribute('open', '');
    await words.locator('summary').click();
    await expect(words).toHaveAttribute('open', '');
    await expect(words.locator('tbody tr')).toHaveCount(13);
    await expect(words.getByRole('rowheader', { name: 'CPGRAMS' })).toBeVisible();
    // footer link opens it from closed
    await words.locator('summary').click();
    await expect(words).not.toHaveAttribute('open', '');
    await page.getByRole('contentinfo').getByRole('link', { name: 'Plain-word guide' }).click();
    await expect(words).toHaveAttribute('open', '');
    // plain labels in the hero card
    await expect(page.getByText('AICTE complaint portal (CSS)')).toBeVisible();
    await expect(page.getByRole('cell', { name: 'Kanpur regional office' })).toBeVisible();
    // no horizontal scroll
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    expect(errors).toEqual([]);
  });

  test('signed-out visitors land on Home at "/", and Sign in goes to /login', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/home$/);
    await page.getByRole('banner').getByRole('link', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('link', { name: 'Back to home' })).toBeVisible();
  });
});
