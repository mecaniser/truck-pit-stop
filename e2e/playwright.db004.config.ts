import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  reporter: 'line',
  timeout: 30_000,
  use: {
    baseURL: process.env.DB004_BASE_URL || 'http://127.0.0.1:5176',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], hasTouch: true } }],
})
