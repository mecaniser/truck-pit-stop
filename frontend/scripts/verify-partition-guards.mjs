import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { partitionArgs } from './test-partitions.mjs'

test('partition rejects missing, duplicate, empty and escaping critical paths', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'ci-partition-'))
  try {
    mkdirSync(path.join(root, 'src'))
    writeFileSync(path.join(root, 'src/one.test.ts'), '')
    for (const entries of [[], ['src/missing.test.ts'], ['src/one.test.ts', 'src/one.test.ts'], ['src/../one.test.ts'], ['--passWithNoTests']]) {
      assert.throws(() => partitionArgs('remaining', entries, root))
    }
    assert.throws(() => partitionArgs('unknown', ['src/one.test.ts'], root))
    assert.deepEqual(partitionArgs('critical', ['src/one.test.ts'], root), ['src/one.test.ts'])
    assert.deepEqual(partitionArgs('remaining', ['src/one.test.ts'], root), ['--exclude', 'src/one.test.ts'])
  } finally {
    rmSync(root, { recursive: true })
  }
})
