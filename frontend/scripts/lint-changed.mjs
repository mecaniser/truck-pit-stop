import { execFileSync, spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..', '..')
const eslintBinary = resolve(repoRoot, 'frontend', 'node_modules', '.bin', 'eslint')
const base = process.env.BASE_SHA
const head = process.env.HEAD_SHA || 'HEAD'
const fallbackBase = `${head}^`

function changedFiles(from) {
  try {
    return execFileSync(
      'git',
      ['diff', '--name-only', '--diff-filter=ACMR', from, head, '--', 'frontend'],
      { cwd: repoRoot, encoding: 'utf8' },
    ).split('\n')
  } catch {
    return []
  }
}

const comparisonBase = base || fallbackBase
const files = changedFiles(comparisonBase)
  .map((file) => file.trim())
  .filter((file) => /\.(ts|tsx)$/.test(file))
  .filter((file) => !file.endsWith('.d.ts'))
  .filter((file) => existsSync(resolve(repoRoot, file)))

if (files.length === 0) {
  console.log('No changed TypeScript frontend files to lint.')
  process.exit(0)
}

function sourceAtRevision(revision, file) {
  try {
    return execFileSync('git', ['show', `${revision}:${file}`], {
      cwd: repoRoot,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    })
  } catch {
    return null
  }
}

function lintSource(source, filename) {
  const result = spawnSync(
    eslintBinary,
    ['eslint', '--stdin', '--stdin-filename', filename, '--format', 'json'],
    { cwd: repoRoot, input: source, encoding: 'utf8' },
  )
  if (result.error) throw result.error
  if (!result.stdout) throw new Error(`ESLint returned no output for ${filename}`)
  const [report] = JSON.parse(result.stdout)
  const lines = source.split('\n')
  return report.messages
    .filter((message) => message.severity === 2)
    .map((message) => ({
      ...message,
      signature: [message.ruleId, message.message, lines[message.line - 1]?.trim() || ''].join('|'),
    }))
}

const regressions = []
for (const file of files) {
  const currentSource = readFileSync(resolve(repoRoot, file), 'utf8')
  const currentProblems = lintSource(currentSource, file)
  const baseSource = sourceAtRevision(comparisonBase, file)
  const baseline = new Set(
    baseSource ? lintSource(baseSource, file).map((problem) => problem.signature) : [],
  )
  regressions.push(...currentProblems.filter((problem) => !baseline.has(problem.signature)).map((problem) => ({ file, ...problem })))
}

if (regressions.length > 0) {
  console.error('This PR introduces new frontend lint violations:')
  for (const problem of regressions) {
    console.error(`${problem.file}:${problem.line}:${problem.column} ${problem.ruleId}: ${problem.message}`)
  }
  process.exit(1)
}

console.log(`No new frontend lint violations across ${files.length} changed file(s).`)
