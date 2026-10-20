import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

export const criticalTests = JSON.parse(readFileSync(new URL('../../.github/critical-tests.json', import.meta.url), 'utf8')).frontend

export function partitionArgs(mode, entries = criticalTests, root = process.cwd()) {
  if (!['critical', 'remaining'].includes(mode)) throw new Error('Unknown test partition')
  if (!Array.isArray(entries) || !entries.length || new Set(entries).size !== entries.length) {
    throw new Error('Critical test list must be nonempty and unique')
  }
  for (const entry of entries) {
    if (typeof entry !== 'string' || !/^src\/[\w./-]+\.(test|spec)\.[cm]?[jt]sx?$/.test(entry)
      || entry.split('/').includes('..') || !existsSync(path.join(root, entry))) {
      throw new Error(`Invalid or missing critical test: ${entry}`)
    }
  }
  return mode === 'critical' ? [...entries] : entries.flatMap(entry => ['--exclude', entry])
}
