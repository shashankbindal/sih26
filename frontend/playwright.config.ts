import { defineConfig } from '@playwright/test';

/** QA e2e. Servers are started by hand (backend :8000, Vite :5173). Reseed before a full run. */
export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.spec\.ts/,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: 'e2e/results.json' }]],
  use: {
    baseURL: process.env.QA_WEB_URL ?? 'http://localhost:5173',
    viewport: { width: 1366, height: 768 },
    actionTimeout: 10_000,
    trace: 'off',
    screenshot: 'off',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
