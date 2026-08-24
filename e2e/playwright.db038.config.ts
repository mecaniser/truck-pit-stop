import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  testMatch: 'db038-parts-operations.spec.ts',
  timeout: 45_000,
  retries: 0,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://127.0.0.1:5181',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm --prefix ../frontend run dev -- --host 127.0.0.1 --port 5181 --strictPort',
    env: {
      DIESELBRIDGE_RUNTIME_BRANCH: 'e2e/db038-parts-operations',
      DIESELBRIDGE_RUNTIME_SHA: '92aed013522c936ddb1c8bfce0cddd1993d665a3',
    },
    url: 'http://127.0.0.1:5181',
    timeout: 120_000,
    reuseExistingServer: false,
  },
})
