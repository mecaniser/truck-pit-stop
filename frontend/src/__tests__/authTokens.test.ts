import { describe, it, expect } from 'vitest'
import { decodeJwtPayload, isTokenExpired, isTokenExpiredOrNearExpiry } from '../lib/authTokens'

function makeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.signature`
}

describe('decodeJwtPayload', () => {
  it('decodes a valid JWT payload', () => {
    const token = makeJwt({ sub: 'user-1', exp: 9999999999 })
    const payload = decodeJwtPayload(token)
    expect(payload).toEqual({ sub: 'user-1', exp: 9999999999 })
  })

  it('returns null for garbage string', () => {
    expect(decodeJwtPayload('not-a-jwt')).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(decodeJwtPayload('')).toBeNull()
  })
})

describe('isTokenExpired', () => {
  it('returns false for far-future expiry', () => {
    const token = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
    expect(isTokenExpired(token)).toBe(false)
  })

  it('returns true for past expiry', () => {
    const token = makeJwt({ exp: Math.floor(Date.now() / 1000) - 10 })
    expect(isTokenExpired(token)).toBe(true)
  })

  it('returns true for missing exp', () => {
    const token = makeJwt({ sub: 'user' })
    expect(isTokenExpired(token)).toBe(true)
  })
})

describe('isTokenExpiredOrNearExpiry', () => {
  it('considers skew window', () => {
    const exp = Math.floor(Date.now() / 1000) + 5
    const token = makeJwt({ exp })
    expect(isTokenExpiredOrNearExpiry(token, 10)).toBe(true) // within 10s skew
    expect(isTokenExpiredOrNearExpiry(token, 0)).toBe(false) // still valid
  })
})
