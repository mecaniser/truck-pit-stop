import { defineConfig, devices } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const repositoryRoot = path.resolve(__dirname, '..')
const candidateSha = execFileSync('git', ['rev-parse', 'HEAD'], {
  cwd: repositoryRoot,
  encoding: 'utf8',
}).trim()

export default defineConfig({
  testDir: './tests',
  testMatch: 'db038-parts-operations.spec.ts',
  grep: /DB-040/,
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
      DIESELBRIDGE_RUNTIME_BRANCH: 'e2e/db040-parts-workspace-distillation',
      DIESELBRIDGE_RUNTIME_SHA: candidateSha,
    },
    url: 'http://127.0.0.1:5181',
    timeout: 120_000,
    reuseExistingServer: false,
  },
})
