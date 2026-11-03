import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  testMatch: 'db151-workspace-flows.spec.ts',
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 8_000 },
  use: { actionTimeout: 8000, screenshot: 'only-on-failure' },
})
