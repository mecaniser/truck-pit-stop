import { execFileSync } from 'node:child_process'
import { partitionArgs } from './test-partitions.mjs'

// Critical files run in Frontend checks. Together the two jobs cover the suite.
execFileSync('npx', ['vitest', 'run', ...partitionArgs('remaining')], { stdio: 'inherit' })
