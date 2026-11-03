import { afterEach, expect, it } from 'vitest'
import { beginSignedOutLogin, captureWorkOSLoginReturn, mayResumeSignedOutLogin } from '../workosLoginReturn'

afterEach(() => { history.replaceState(null, '', '/'); captureWorkOSLoginReturn(); sessionStorage.clear() })

it('permits one matching callback for the starting session and removes the marker from history', () => {
  const target = new URL(beginSignedOutLogin('/api/v1/auth/workos/login?return_to=%2Fdashboard', 'old-generation'))
  const nonce = target.searchParams.get('browser_attempt')!
  expect(target.searchParams.get('return_to')).toBe('/dashboard')
  history.replaceState(null, '', '/dashboard?work_view=closeout')
  captureWorkOSLoginReturn()
  expect(mayResumeSignedOutLogin('old-generation')).toBe(false)
  history.replaceState(null, '', '/dashboard?work_view=closeout&db_login_completed=' + nonce + '#work')
  captureWorkOSLoginReturn()
  expect(location.search + location.hash).toBe('?work_view=closeout#work')
  expect(mayResumeSignedOutLogin('old-generation')).toBe(true)
  expect(mayResumeSignedOutLogin('new-generation')).toBe(false)
  history.replaceState(null, '', '/dashboard?db_login_completed=' + nonce)
  captureWorkOSLoginReturn()
  expect(mayResumeSignedOutLogin('old-generation')).toBe(false)
})

it('rejects a duplicate marker even when it includes the tab nonce', () => {
  const url = new URL(beginSignedOutLogin('/api/v1/auth/workos/login', 'session'))
  const nonce = url.searchParams.get('browser_attempt')
  history.replaceState(null, '', '/dashboard?db_login_completed=' + nonce + '&db_login_completed=another')
  captureWorkOSLoginReturn()
  expect(mayResumeSignedOutLogin('session')).toBe(false)
})
