// Reuse one exact installation within a workflow run, never across PRs/runs.
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const digest = file => createHash('sha256').update(readFileSync(file)).digest('hex')
export function identity(root, env = process.env) {
  for (const key of ['GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA']) {
    if (!env[key]) throw new Error(`Missing identity: ${key}`)
  }
  return {
    run: env.GITHUB_RUN_ID, attempt: env.GITHUB_RUN_ATTEMPT, sha: env.GITHUB_SHA,
    node: process.version, abi: process.versions.modules, platform: process.platform,
    arch: process.arch, libc: process.report.getReport().header.glibcVersionRuntime ?? null,
    package: digest(path.join(root, 'package.json')),
    lock: digest(path.join(root, 'package-lock.json')),
  }
}
export function pack(root, directory, env = process.env) {
  const expected = identity(root, env)
  if (!existsSync(path.join(root, 'node_modules'))) throw new Error('Installation missing')
  mkdirSync(directory, { recursive: true })
  const archive = path.join(directory, 'dependencies.tar.gz')
  execFileSync('tar', ['-czf', archive, '-C', root, 'node_modules'])
  writeFileSync(path.join(directory, 'identity.json'), JSON.stringify({ ...expected, archive: digest(archive) }))
}
export function restore(root, directory, env = process.env) {
  const expected = identity(root, env)
  const actual = JSON.parse(readFileSync(path.join(directory, 'identity.json'), 'utf8'))
  for (const [key, value] of Object.entries(expected)) {
    if (actual[key] !== value) throw new Error(`Dependency identity mismatch: ${key}`)
  }
  const archive = path.join(directory, 'dependencies.tar.gz')
  if (actual.archive !== digest(archive)) throw new Error('Dependency archive checksum mismatch')
  if (existsSync(path.join(root, 'node_modules'))) throw new Error('Refusing to mix installations')
  const entries = execFileSync('tar', ['-tzf', archive], { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 }).trim().split('\n')
  if (!entries.length || entries.some(entry => !entry.startsWith('node_modules/') || entry.split('/').includes('..'))) {
    throw new Error('Unexpected dependency archive path')
  }
  execFileSync('tar', ['-xzf', archive, '-C', root])
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const [mode, directory] = process.argv.slice(2)
  if (!['pack', 'restore'].includes(mode) || !directory) throw new Error('Expected pack|restore DIRECTORY')
  ;({ pack, restore })[mode](process.cwd(), path.resolve(directory))
}
