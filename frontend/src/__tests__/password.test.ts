import { describe, it, expect } from 'vitest'
import { generateMechanicPassword } from '../utils/password'

describe('generateMechanicPassword', () => {
  it('generates from first name and last 4 phone digits', () => {
    expect(generateMechanicPassword('john', '5551234567')).toBe('John@4567')
  })

  it('capitalizes first letter, lowercases rest', () => {
    expect(generateMechanicPassword('ALICE', '5551230000')).toBe('Alice@0000')
  })

  it('uses fallback for empty name', () => {
    expect(generateMechanicPassword('', '5551234567')).toBe('Mechanic@4567')
  })

  it('uses 0000 for empty phone', () => {
    expect(generateMechanicPassword('Bob', '')).toBe('Bob@0000')
  })

  it('pads to minimum 8 characters', () => {
    const pw = generateMechanicPassword('Jo', '1234')
    expect(pw.length).toBeGreaterThanOrEqual(8)
  })

  it('includes @ separator', () => {
    expect(generateMechanicPassword('Test', '5551234567')).toContain('@')
  })
})
