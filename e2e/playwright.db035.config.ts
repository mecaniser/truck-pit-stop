import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.DB035_BASE_URL || 'http://127.0.0.1:5178'

export default defineConfig({
  testDir: './tests',
  testMatch: 'db035-presentation.spec.ts',
  reporter: 'line',
  timeout: 45_000,
  expect: { timeout: 8_000 },
  use: {
    baseURL,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.DB035_BASE_URL ? undefined : {
    command: 'npm --prefix ../frontend run dev -- --host 127.0.0.1 --port 5178 --strictPort',
    url: 'http://127.0.0.1:5178',
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
