import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { partitionArgs } from './test-partitions.mjs'

const collect = args => {
  const directory = mkdtempSync(path.join(tmpdir(), 'vitest-partition-'))
  try {
    const output = path.join(directory, 'files.json')
    execFileSync('npx', ['vitest', 'list', '--filesOnly', `--json=${output}`, ...args], { stdio: 'inherit' })
    return new Set(JSON.parse(readFileSync(output, 'utf8')).map(item => item.file))
  } finally {
    rmSync(directory, { recursive: true })
  }
}
const all = collect([])
const critical = collect(partitionArgs('critical'))
const remaining = collect(partitionArgs('remaining'))
assert.ok(all.size && critical.size && remaining.size, 'Empty test partition')
assert.deepEqual([...critical].filter(file => remaining.has(file)), [], 'Test partitions overlap')
assert.deepEqual([...new Set([...critical, ...remaining])].sort(), [...all].sort(), 'Test partition coverage differs from full suite')
console.log(`Frontend partition coverage: ${critical.size} critical + ${remaining.size} remaining = ${all.size} files, no overlap`)
