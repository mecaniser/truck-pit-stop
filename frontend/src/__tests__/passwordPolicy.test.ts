import { describe, it, expect } from 'vitest'
import { getPasswordValidationError } from '../lib/passwordPolicy'

describe('getPasswordValidationError', () => {
  it('returns null for strong password', () => {
    expect(getPasswordValidationError('MyStr0ng@Pass!')).toBeNull()
  })

  it('rejects too short', () => {
    const err = getPasswordValidationError('Aa1@')
    expect(err).toContain('at least 8 characters')
  })

  it('rejects missing uppercase', () => {
    const err = getPasswordValidationError('nouppercas3@')
    expect(err).toContain('one uppercase letter')
  })

  it('rejects missing lowercase', () => {
    const err = getPasswordValidationError('ALLCAPS123@!')
    expect(err).toContain('one lowercase letter')
  })

  it('rejects missing digit', () => {
    const err = getPasswordValidationError('NoDigits@Here!')
    expect(err).toContain('one digit')
  })

  it('rejects missing special char', () => {
    const err = getPasswordValidationError('NoSpecial1Char')
    expect(err).toContain('one special character')
  })

  it('rejects common password', () => {
    const err = getPasswordValidationError('P@ssw0rd')
    expect(err).toContain('common password')
  })

  it('combines multiple errors', () => {
    const err = getPasswordValidationError('abc')
    expect(err).toContain('at least 8 characters')
    expect(err).toContain('one uppercase letter')
    expect(err).toContain('one digit')
  })
})
