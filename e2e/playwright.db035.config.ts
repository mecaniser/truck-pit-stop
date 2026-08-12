import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  testMatch: 'db035-presentation.spec.ts',
  reporter: 'line',
  timeout: 45_000,
  expect: { timeout: 8_000 },
  use: {
    baseURL: 'http://127.0.0.1:5178',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm --prefix ../frontend run dev -- --host 127.0.0.1 --port 5178',
    url: 'http://127.0.0.1:5178',
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
