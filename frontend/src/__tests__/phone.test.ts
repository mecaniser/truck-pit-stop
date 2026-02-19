import { describe, it, expect } from 'vitest'
import { formatUSPhone, isValidUSPhone } from '../utils/phone'

describe('formatUSPhone', () => {
  it('formats 10 digits to (XXX) XXX-XXXX', () => {
    expect(formatUSPhone('5551234567')).toBe('(555) 123-4567')
  })

  it('strips country code prefix 1', () => {
    expect(formatUSPhone('15551234567')).toBe('(555) 123-4567')
  })

  it('partial 3 digits', () => {
    expect(formatUSPhone('555')).toBe('(555')
  })

  it('partial 6 digits', () => {
    expect(formatUSPhone('555123')).toBe('(555) 123')
  })

  it('strips non-digit chars', () => {
    expect(formatUSPhone('(555) 123-4567')).toBe('(555) 123-4567')
  })

  it('returns empty for empty string', () => {
    expect(formatUSPhone('')).toBe('')
  })
})

describe('isValidUSPhone', () => {
  it('accepts null/undefined', () => {
    expect(isValidUSPhone(null)).toBe(true)
    expect(isValidUSPhone(undefined)).toBe(true)
  })

  it('accepts 10-digit number', () => {
    expect(isValidUSPhone('5551234567')).toBe(true)
  })

  it('accepts 11-digit starting with 1', () => {
    expect(isValidUSPhone('15551234567')).toBe(true)
  })

  it('accepts formatted phone', () => {
    expect(isValidUSPhone('(555) 123-4567')).toBe(true)
  })

  it('rejects 9 digits', () => {
    expect(isValidUSPhone('555123456')).toBe(false)
  })

  it('rejects 12 digits', () => {
    expect(isValidUSPhone('155512345678')).toBe(false)
  })
})
