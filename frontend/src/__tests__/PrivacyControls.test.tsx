import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PrivacyControls, { CookiePrivacySettings } from '../components/PrivacyControls'
import { PolicyLinks } from '../features/landing/PublicPolicyPage'
import { PRIVACY_KEY, readPrivacyChoice, savePrivacyChoice } from '../lib/privacyPreferences'

beforeEach(() => {
  localStorage.clear()
  Object.defineProperty(navigator, 'globalPrivacyControl', { value: false, configurable: true })
  Object.defineProperty(navigator, 'doNotTrack', { value: '0', configurable: true })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })
const mount = (entry: 'footer' | 'settings' | null = 'footer', path = '/') => render(<MemoryRouter initialEntries={[path]}>
  <PrivacyControls />
  {entry === 'footer' && <PolicyLinks />}
  {entry === 'settings' && <CookiePrivacySettings />}
  <Link to="/dashboard/garage/inventory">Go to Inventory</Link>
  <Link to="/?view=another">Change view</Link>
</MemoryRouter>)
const open = () => fireEvent.click(screen.getByRole('button', { name: 'Cookie settings' }))

describe('necessary-only privacy choices', () => {
  it('does not interrupt a fresh workspace or render a floating launcher', () => {
    mount(null, '/dashboard/garage/inventory')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cookie settings' })).not.toBeInTheDocument()
    expect(document.querySelector('#google-analytics-tag')).toBeNull()
  })
  it.each(['footer', 'settings'] as const)('opens only on request from %s', entry => {
    mount(entry)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    open()
    expect(screen.getByRole('dialog', { name: 'Your privacy choices' })).toBeVisible()
    expect(screen.getByText(/Optional analytics is off/)).toBeVisible()
    expect(screen.queryByRole('button', { name: /accept analytics/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close settings' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cookie settings' })).toHaveFocus()
    expect(readPrivacyChoice()).toBeNull()
  })
  it('supports keyboard opening and Escape with focus returned to its entry point', async () => {
    const user = userEvent.setup()
    mount()
    screen.getByRole('button', { name: 'Cookie settings' }).focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('heading', { name: 'Your privacy choices' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cookie settings' })).toHaveFocus()
  })
  it('removes old analytics cookies without touching authentication and saves necessary-only preference', () => {
    document.cookie = '_ga=test; path=/'
    document.cookie = 'session=keep; path=/'
    mount()
    expect(document.cookie).not.toContain('_ga=')
    expect(document.cookie).toContain('session=keep')
    open()
    fireEvent.click(screen.getByRole('button', { name: 'Keep optional cookies off' }))
    expect(readPrivacyChoice()).toBe('rejected')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('honors the browser privacy signal without prompting', () => {
    Object.defineProperty(navigator, 'globalPrivacyControl', { value: true, configurable: true })
    expect(readPrivacyChoice()).toBe('rejected')
    mount(); expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); open()
    expect(screen.getByText(/browser privacy signal is on/)).toBeVisible()
  })
  it.each(['{broken', '{}', JSON.stringify({version:1,choice:'rejected',at:0}), JSON.stringify({version:1,choice:'accepted',at:Date.now()})])('does not prompt for invalid, expired, or old acceptance: %s', value => {
    localStorage.setItem(PRIVACY_KEY, value)
    expect(readPrivacyChoice()).toBeNull()
    mount()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('remains dismissible when browser storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    mount(); open()
    fireEvent.click(screen.getByRole('button', { name: 'Keep optional cookies off' }))
    expect(screen.getByRole('status')).toHaveTextContent('Optional analytics remains off')
    fireEvent.click(screen.getByRole('button', { name: 'Close settings' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(readPrivacyChoice()).toBeNull()
  })
  it('does not reopen when a preference is removed in another tab', () => {
    savePrivacyChoice('rejected'); mount()
    act(() => { localStorage.removeItem(PRIVACY_KEY); window.dispatchEvent(new StorageEvent('storage', { key: PRIVACY_KEY })) })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it.each(['Go to Inventory', 'Change view'])('closes on route or query navigation: %s', name => {
    mount(); open()
    fireEvent.click(screen.getByRole('link', { name }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('keeps the OAuth callback free of privacy UI', () => {
    render(<MemoryRouter initialEntries={['/fleet/motive/callback']}><PrivacyControls /></MemoryRouter>)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
