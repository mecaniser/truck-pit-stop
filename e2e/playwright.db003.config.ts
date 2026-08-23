import { defineConfig, devices } from '@playwright/test'

const runtimeEnvironment = {
  DIESELBRIDGE_RUNTIME_BRANCH: 'e2e/db003-playwright',
  DIESELBRIDGE_RUNTIME_SHA: 'a600eb1314630a51be8420f9cee043bc1406ac28',
}

export default defineConfig({
  testDir: './tests',
  testMatch: ['db003-authorization.spec.ts', 'customer-portal-mobile.spec.ts'],
  timeout: 30_000,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'db003-chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'cd ../frontend && exec npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',
    env: runtimeEnvironment,
    port: 5174,
    timeout: 30_000,
    reuseExistingServer: false,
  },
})
