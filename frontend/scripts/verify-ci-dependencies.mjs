import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { pack, restore } from './ci-dependencies.mjs'
const env = { GITHUB_RUN_ID: '1', GITHUB_RUN_ATTEMPT: '1', GITHUB_SHA: 'abc' }
function fixture(t) {
  const base = mkdtempSync(path.join(tmpdir(), 'ci-dependency-test-'))
  t.after(() => rmSync(base, { recursive: true, force: true }))
  const source = path.join(base, 'source'), target = path.join(base, 'target'), archive = path.join(base, 'archive')
  for (const root of [source, target]) {
    mkdirSync(root)
    writeFileSync(path.join(root, 'package.json'), '{}')
    writeFileSync(path.join(root, 'package-lock.json'), '{"lockfileVersion":3}')
  }
  mkdirSync(path.join(source, 'node_modules'))
  writeFileSync(path.join(source, 'node_modules', 'proof'), 'installed')
  pack(source, archive, env)
  return { target, archive }
}
test('exact identity restores the installation and refuses mixing', t => {
  const { target, archive } = fixture(t)
  restore(target, archive, env)
  assert.equal(readFileSync(path.join(target, 'node_modules', 'proof'), 'utf8'), 'installed')
  assert.throws(() => restore(target, archive, env), /mix installations/)
})
for (const field of ['run', 'attempt', 'sha', 'node', 'abi', 'platform', 'arch', 'libc', 'package', 'lock', 'archive']) {
  test(`rejects changed ${field}`, t => {
    const { target, archive } = fixture(t)
    const file = path.join(archive, 'identity.json')
    const identity = JSON.parse(readFileSync(file))
    identity[field] = 'mismatch'
    writeFileSync(file, JSON.stringify(identity))
    assert.throws(() => restore(target, archive, env), /mismatch/)
  })
}
test('missing run identity fails closed', t => {
  const { target, archive } = fixture(t)
  assert.throws(() => restore(target, archive, {}), /Missing identity/)
})
