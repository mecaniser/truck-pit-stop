import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  reporter: 'line',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:5174',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], hasTouch: true } }],
})
