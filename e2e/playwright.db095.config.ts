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
  testMatch: 'db095-parts-sync-freshness.spec.ts',
  grep: /DB-095/,
  timeout: 45_000,
  retries: 0,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://127.0.0.1:5190',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Port 5190 is isolated from the shared 5173 runtime and from 5181, which
  // another worktree holds.
  webServer: {
    command: 'npm --prefix ../frontend run dev -- --host 127.0.0.1 --port 5190 --strictPort',
    env: {
      DIESELBRIDGE_RUNTIME_BRANCH: 'e2e/db095-parts-sync-freshness',
      DIESELBRIDGE_RUNTIME_SHA: candidateSha,
    },
    url: 'http://127.0.0.1:5190',
    timeout: 120_000,
    reuseExistingServer: true,
  },
})
