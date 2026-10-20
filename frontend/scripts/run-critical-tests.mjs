import { execFileSync } from 'node:child_process'
import process from 'node:process'
import { partitionArgs } from './test-partitions.mjs'

execFileSync(process.execPath, ['scripts/check-runtime-identity.mjs'], { stdio: 'inherit' })

execFileSync('npx', ['vitest', 'run', ...partitionArgs('critical')], { stdio: 'inherit' })
