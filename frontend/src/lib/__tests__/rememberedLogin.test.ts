import { afterEach, describe, expect, it } from 'vitest'
import {
  getLastLoginMethod,
  getRememberedLogin,
  setLastLoginMethod,
  updateRememberedLogin,
} from '../rememberedLogin'

afterEach(() => {
  window.localStorage.clear()
})

describe('rememberedLogin', () => {
  it('persists the email only when "remember me" is checked', () => {
    updateRememberedLogin('driver@example.com', true)
    expect(getRememberedLogin()).toEqual({ email: 'driver@example.com', rememberMe: true })
  })

  it('never stores a password (only email + flag keys exist)', () => {
    updateRememberedLogin('driver@example.com', true)
    const keys = Object.keys(window.localStorage)
    expect(keys).toEqual(
      expect.arrayContaining(['db.login.rememberedEmail', 'db.login.rememberMe'])
    )
    expect(keys.some((k) => k.toLowerCase().includes('password'))).toBe(false)
  })

  it('clears the remembered email when the box is unchecked', () => {
    updateRememberedLogin('driver@example.com', true)
    updateRememberedLogin('driver@example.com', false)
    expect(getRememberedLogin()).toEqual({ email: '', rememberMe: false })
  })

  it('does not surface a stale email if the flag is absent', () => {
    window.localStorage.setItem('db.login.rememberedEmail', 'left@over.com')
    expect(getRememberedLogin()).toEqual({ email: '', rememberMe: false })
  })

  it('round-trips the last login method', () => {
    expect(getLastLoginMethod()).toBeNull()
    setLastLoginMethod('workos')
    expect(getLastLoginMethod()).toBe('workos')
    setLastLoginMethod('password')
    expect(getLastLoginMethod()).toBe('password')
  })
})
