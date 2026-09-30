import { describe, expect, it } from 'vitest'
import { captureMotiveCallback, takeMotiveCallback } from '../motiveCallback'

describe('Motive return privacy before session bootstrap', () => {
  it('removes callback query data immediately and exposes it only once in memory', () => {
    window.history.replaceState({}, '', '/fleet/motive/callback?code=fixture-code&state=fixture-state')
    const beforeLocal = JSON.stringify(localStorage)
    const beforeSession = JSON.stringify(sessionStorage)
    captureMotiveCallback()
    expect(window.location.pathname).toBe('/fleet/motive/callback')
    expect(window.location.search).toBe('')
    expect(takeMotiveCallback()).toEqual({ code: 'fixture-code', state: 'fixture-state', error: null })
    expect(takeMotiveCallback()).toEqual({ code: null, state: null, error: null })
    expect(JSON.stringify(localStorage)).toBe(beforeLocal)
    expect(JSON.stringify(sessionStorage)).toBe(beforeSession)
  })
  it('leaves normal route queries intact', () => {
    window.history.replaceState({}, '', '/fleet?company=fixture-company')
    captureMotiveCallback()
    expect(window.location.search).toBe('?company=fixture-company')
  })
})
