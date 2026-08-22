import assert from 'node:assert/strict'
import process from 'node:process'
import { resolveConfig } from 'vite'

const publicBranch = 'VITE_DIESELBRIDGE_RUNTIME_BRANCH'
const publicSha = 'VITE_DIESELBRIDGE_RUNTIME_SHA'
const privateBranch = 'DIESELBRIDGE_RUNTIME_BRANCH'
const privateSha = 'DIESELBRIDGE_RUNTIME_SHA'
const branch = 'codex/db037-runtime-check'
const sha = 'e'.repeat(40)

const setCanaries = () => {
  process.env[privateBranch] = branch
  process.env[privateSha] = sha
  process.env[publicBranch] = 'must-not-be-exposed'
  process.env[publicSha] = 'f'.repeat(40)
}

const assertPrivate = (config) => {
  assert.equal(config.env[publicBranch], undefined)
  assert.equal(config.env[publicSha], undefined)
  assert.equal(config.define?.[`import.meta.env.${publicBranch}`], undefined)
  assert.equal(config.define?.[`import.meta.env.${publicSha}`], undefined)
}

try {
  setCanaries()
  assertPrivate(await resolveConfig({}, 'serve', 'test'))

  setCanaries()
  assertPrivate(await resolveConfig({}, 'build', 'production'))

  setCanaries()
  const development = await resolveConfig({}, 'serve', 'development')
  assert.equal(development.env[publicBranch], undefined)
  assert.equal(development.env[publicSha], undefined)
  assert.equal(development.define[`import.meta.env.${publicBranch}`], JSON.stringify(branch))
  assert.equal(development.define[`import.meta.env.${publicSha}`], JSON.stringify(sha))
} finally {
  for (const key of [publicBranch, publicSha, privateBranch, privateSha]) {
    delete process.env[key]
  }
}

console.log('Runtime identity configuration check passed')
