import { execFileSync } from 'node:child_process'
import { partitionArgs } from './test-partitions.mjs'

// Critical files run in Frontend checks. Together the two jobs cover the suite.
// Each disposable CI VM has two CPUs. Bound this partition to two isolated
// workers; retain serial critical checks and unchanged per-test deadlines.
execFileSync('npx', ['vitest', 'run', '--maxWorkers=2', '--isolate', ...partitionArgs('remaining')], { stdio: 'inherit' })
