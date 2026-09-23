/** DB-076: the build must write the stamp the backend serves. */
import { describe, expect, it } from 'vitest'
import { buildStampPlugin } from '../../scripts/buildStampPlugin.mjs'

describe('buildStampPlugin', () => {
  it('writes a 40-hex sha and an ISO timestamp into the bundle', () => {
    const emitted: Record<string, string> = {}
    const plugin = buildStampPlugin({ sha: 'f'.repeat(40), now: () => '2026-09-23T12:00:00.000Z' })
    plugin.generateBundle.call({ emitFile: (f: { fileName: string; source: string }) => { emitted[f.fileName] = f.source } })
    expect(JSON.parse(emitted['build-version.json'])).toEqual({
      sha: 'f'.repeat(40),
      built_at: '2026-09-23T12:00:00.000Z',
    })
  })

  it('refuses a sha that is not 40 lowercase hex, keeping the existing guard', () => {
    expect(() => buildStampPlugin({ sha: 'not-a-sha', now: () => '2026-09-23T12:00:00.000Z' }))
      .toThrow(/40 lowercase hex/)
  })

  it('emits an unknown stamp rather than failing the build when no sha is available', () => {
    const emitted: Record<string, string> = {}
    const plugin = buildStampPlugin({ sha: '', now: () => '2026-09-23T12:00:00.000Z' })
    plugin.generateBundle.call({ emitFile: (f: { fileName: string; source: string }) => { emitted[f.fileName] = f.source } })
    expect(JSON.parse(emitted['build-version.json']).sha).toBeNull()
  })
})
