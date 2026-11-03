import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PrivacyControls from '../components/PrivacyControls'
import { PRIVACY_KEY, readPrivacyChoice, savePrivacyChoice } from '../lib/privacyPreferences'

beforeEach(() => {
  localStorage.clear()
  Object.defineProperty(navigator, 'globalPrivacyControl', { value: false, configurable: true })
  Object.defineProperty(navigator, 'doNotTrack', { value: '0', configurable: true })
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers() })
const mount = (path = '/') => render(<MemoryRouter initialEntries={[path]}><PrivacyControls /></MemoryRouter>)

describe('necessary-only privacy choices', () => {
  it('explains analytics is disabled and does not offer a meaningless accept action', () => {
    mount()
    expect(screen.getByText(/Optional analytics is off/)).toBeVisible()
    expect(screen.queryByRole('button', { name: /accept analytics/i })).not.toBeInTheDocument()
    expect(document.querySelector('#google-analytics-tag')).toBeNull()
  })
  it('removes old analytics cookies without touching authentication and saves necessary-only preference', () => {
    document.cookie = '_ga=test; path=/'
    document.cookie = 'session=keep; path=/'
    mount()
    expect(document.cookie).not.toContain('_ga=')
    expect(document.cookie).toContain('session=keep')
    fireEvent.click(screen.getByRole('button', { name: 'Keep optional cookies off' }))
    expect(readPrivacyChoice()).toBe('rejected')
    expect(screen.queryByRole('button', { name: 'Keep optional cookies off' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cookie settings' }))
    expect(screen.getByRole('button', { name: 'Keep optional cookies off' })).toBeVisible()
  })
  it('honors browser privacy signals', () => {
    Object.defineProperty(navigator, 'globalPrivacyControl', { value: true, configurable: true })
    expect(readPrivacyChoice()).toBe('rejected')
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Cookie settings' }))
    expect(screen.getByText(/browser privacy signal is on/)).toBeVisible()
  })
  it.each(['{broken', '{}', JSON.stringify({version:1,choice:'rejected',at:0}), JSON.stringify({version:1,choice:'accepted',at:Date.now()})])('does not treat invalid, expired, or old analytics acceptance as a current preference', value => {
    localStorage.setItem(PRIVACY_KEY, value)
    expect(readPrivacyChoice()).toBeNull()
  })
  it('does not resurrect prior analytics acceptance when saving fails', () => {
    localStorage.setItem(PRIVACY_KEY, JSON.stringify({version:1,choice:'accepted',at:Date.now()}))
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Keep optional cookies off' }))
    expect(screen.getByRole('status')).toHaveTextContent('Optional analytics remains off')
    expect(readPrivacyChoice()).toBeNull()
  })
  it('responds to cross-tab preference removal', () => {
    savePrivacyChoice('rejected'); mount()
    act(() => { localStorage.removeItem(PRIVACY_KEY); window.dispatchEvent(new StorageEvent('storage', { key: PRIVACY_KEY })) })
    expect(screen.getByRole('button', { name: 'Keep optional cookies off' })).toBeVisible()
  })
  it('keeps the OAuth callback free of privacy UI', () => {
    const { container } = mount('/fleet/motive/callback')
    expect(container).toBeEmptyDOMElement()
  })
})
