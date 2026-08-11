import { defineConfig, devices } from '@playwright/test'

const backendPython = process.env.CI ? 'python' : 'venv/bin/python'
const backendCommand = `mkdir -p test-results && cd ../backend && exec ${backendPython} -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > ../e2e/test-results/backend-server.log 2>&1`
const frontendCommand = 'mkdir -p test-results && cd ../frontend && exec npm run dev -- --host 127.0.0.1 > ../e2e/test-results/frontend-server.log 2>&1'

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: backendCommand,
      port: 8000,
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: frontendCommand,
      port: 5173,
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
})
