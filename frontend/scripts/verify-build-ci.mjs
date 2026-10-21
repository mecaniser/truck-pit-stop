import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const script = fileURLToPath(new URL('./build-ci.mjs', import.meta.url))
for (const codes of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
  test(`both build gates run, exits ${codes}`, t => {
    const root = mkdtempSync(path.join(tmpdir(), 'ci-build-test-'))
    t.after(() => rmSync(root, { recursive: true, force: true }))
    for (const [index, command] of ['typescript/bin/tsc', 'vite/bin/vite.js'].entries()) {
      const file = path.join(root, 'node_modules', command)
      mkdirSync(path.dirname(file), { recursive: true })
      writeFileSync(file, `require('fs').writeFileSync('${index}.txt', JSON.stringify(process.argv.slice(2)));process.exit(${codes[index]})`)
    }
    const result = spawnSync(process.execPath, [script], { cwd: root })
    assert.equal(result.status, codes.some(Boolean) ? 1 : 0)
    assert.equal(readFileSync(path.join(root, '0.txt'), 'utf8'), '[]')
    assert.equal(readFileSync(path.join(root, '1.txt'), 'utf8'), '["build"]')
  })
}
