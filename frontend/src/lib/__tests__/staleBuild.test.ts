/** DB-076: deciding when a long-lived tab may reload itself. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  checkBuildVersion,
  isDirtyFormRegistered,
  registerDirtyForm,
  resetStaleBuild,
  shouldReloadSilently,
} from '../staleBuild'

afterEach(() => { resetStaleBuild(); vi.restoreAllMocks() })

describe('shouldReloadSilently', () => {
  it('reloads a clean idle page, which is the whole point', () => {
    expect(shouldReloadSilently({ mutationsInFlight: 0, dirtyForms: 0 })).toBe(true)
  })

  it('refuses while a form is dirty, so typed work is never destroyed', () => {
    expect(shouldReloadSilently({ mutationsInFlight: 0, dirtyForms: 1 })).toBe(false)
  })

  it('refuses while a mutation is in flight, so a save is never cut off', () => {
    expect(shouldReloadSilently({ mutationsInFlight: 1, dirtyForms: 0 })).toBe(false)
  })
})

describe('dirty form registry', () => {
  it('tracks a dirty form and releases it', () => {
    const release = registerDirtyForm()
    expect(isDirtyFormRegistered()).toBe(true)
    release()
    expect(isDirtyFormRegistered()).toBe(false)
  })

  it('stays dirty until every registered form releases', () => {
    const a = registerDirtyForm()
    const b = registerDirtyForm()
    a()
    expect(isDirtyFormRegistered()).toBe(true)
    b()
    expect(isDirtyFormRegistered()).toBe(false)
  })
})

describe('checkBuildVersion', () => {
  beforeEach(() => { resetStaleBuild() })

  it('reports stale when the served sha differs from the running one', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ sha: 'b'.repeat(40), built_at: '2026-09-23T12:00:00Z' }),
    }))
    expect(await checkBuildVersion('a'.repeat(40))).toBe('stale')
  })

  it('reports current when the shas match', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ sha: 'a'.repeat(40), built_at: '2026-09-23T12:00:00Z' }),
    }))
    expect(await checkBuildVersion('a'.repeat(40))).toBe('current')
  })

  it('reports unknown on a null sha, so an unbuilt deploy never reloads anyone', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ sha: null, built_at: null }),
    }))
    expect(await checkBuildVersion('a'.repeat(40))).toBe('unknown')
  })

  it('reports unknown when offline rather than treating it as staleness', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    expect(await checkBuildVersion('a'.repeat(40))).toBe('unknown')
  })

  it('reports unknown when the SPA fallback returns HTML instead of JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => { throw new SyntaxError('Unexpected token <') },
    }))
    expect(await checkBuildVersion('a'.repeat(40))).toBe('unknown')
  })

  it('reports unknown when the running build has no sha of its own', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ sha: 'b'.repeat(40), built_at: '2026-09-23T12:00:00Z' }),
    }))
    expect(await checkBuildVersion(null)).toBe('unknown')
  })
})
