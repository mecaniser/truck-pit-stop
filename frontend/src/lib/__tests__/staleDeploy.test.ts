import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  isStaleChunkError,
  lazyRouteLoader,
  resetStaleDeploy,
  startStaleDeployWatch,
  useStaleDeploy,
} from '../staleDeploy'

describe('isStaleChunkError', () => {
  it('recognizes the Chrome dynamic-import failure', () => {
    expect(isStaleChunkError(new TypeError('Failed to fetch dynamically imported module: https://x/assets/MyGaragePage-BqMbfKJl.js'))).toBe(true)
  })

  it('recognizes the Safari and Firefox wordings', () => {
    expect(isStaleChunkError(new TypeError('Importing a module script failed.'))).toBe(true)
    expect(isStaleChunkError(new TypeError('error loading dynamically imported module'))).toBe(true)
  })

  it('recognizes a stale CSS chunk served as JSON by the API fallback', () => {
    expect(isStaleChunkError(new TypeError("Refused to apply style from 'https://x/assets/index-gQi0X1qP.css' because its MIME type ('application/json') is not a supported stylesheet MIME type"))).toBe(true)
  })

  it('does not treat an ordinary network or app error as a stale deploy', () => {
    expect(isStaleChunkError(new TypeError('Failed to fetch'))).toBe(false)
    expect(isStaleChunkError(new Error('Request failed with status code 401'))).toBe(false)
    expect(isStaleChunkError(undefined)).toBe(false)
  })
})

describe('startStaleDeployWatch', () => {
  afterEach(() => { resetStaleDeploy(); vi.restoreAllMocks() })

  it('flags a stale deploy when Vite reports a preload error', () => {
    const stop = startStaleDeployWatch()
    window.dispatchEvent(new Event('vite:preloadError'))
    expect(useStaleDeploy.getState().stale).toBe(true)
    stop()
  })

  it('flags a stale deploy from an unhandled stale chunk rejection', () => {
    const stop = startStaleDeployWatch()
    window.dispatchEvent(new CustomEvent('unhandledrejection', {
      detail: new TypeError('Failed to fetch dynamically imported module: /assets/MyGaragePage-BqMbfKJl.js'),
    }) as unknown as Event)
    expect(useStaleDeploy.getState().stale).toBe(true)
    stop()
  })

  it('ignores an unhandled rejection that is not a stale chunk', () => {
    const stop = startStaleDeployWatch()
    window.dispatchEvent(new CustomEvent('unhandledrejection', {
      detail: new Error('Request failed with status code 401'),
    }) as unknown as Event)
    expect(useStaleDeploy.getState().stale).toBe(false)
    stop()
  })

  it('stops listening once the watch is torn down', () => {
    const stop = startStaleDeployWatch()
    stop()
    window.dispatchEvent(new Event('vite:preloadError'))
    expect(useStaleDeploy.getState().stale).toBe(false)
  })
})

describe('lazyRoute', () => {
  afterEach(() => { resetStaleDeploy() })

  it('flags a stale deploy when a route chunk is gone, the way React.lazy surfaces it', async () => {
    const loader = lazyRouteLoader(() => Promise.reject(
      new TypeError('Failed to fetch dynamically imported module: /assets/MyGaragePage-BqMbfKJl.js'),
    ))
    await expect(loader()).rejects.toThrow(/dynamically imported module/)
    expect(useStaleDeploy.getState().stale).toBe(true)
  })

  it('leaves the flag alone when a route chunk throws a genuine app error', async () => {
    const loader = lazyRouteLoader(() => Promise.reject(new Error('boom in module body')))
    await expect(loader()).rejects.toThrow('boom in module body')
    expect(useStaleDeploy.getState().stale).toBe(false)
  })

  it('passes a healthy module through untouched', async () => {
    const mod = { default: () => null }
    const loader = lazyRouteLoader(() => Promise.resolve(mod))
    await expect(loader()).resolves.toBe(mod)
    expect(useStaleDeploy.getState().stale).toBe(false)
  })
})
