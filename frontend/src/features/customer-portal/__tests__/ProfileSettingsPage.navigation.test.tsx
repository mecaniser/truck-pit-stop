import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ProfileSettingsPage from '../ProfileSettingsPage'

vi.mock('@/stores/authStore', () => ({ getAuthenticatedSessionIdentity: () => '', useAuthStore: () => ({ user: { first_name: 'Test', last_name: 'Customer', email: 'test@example.com' } }) }))
vi.mock('../PaymentMethodsCard', () => ({ default: () => <h2>Saved card fixture</h2> }))
function LocationProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  return <><output data-testid="location">{location.search}</output><button onClick={() => navigate('?tab=notifications')}>External navigation</button></>
}
function mount(query = '?tab=payments&from=invoice') {
  render(<MemoryRouter initialEntries={['/portal/profile' + query]}><QueryClientProvider client={new QueryClient()}><ProfileSettingsPage /><LocationProbe /></QueryClientProvider></MemoryRouter>)
}
describe('account settings navigation', () => {
  it('groups all seven sections and preserves unrelated query parameters', () => {
    mount()
    const nav = screen.getByRole('navigation', { name: 'Account sections' })
    expect(within(nav).getAllByRole('button')).toHaveLength(8)
    for (const name of ['Account', 'Preferences', 'Business']) expect(within(nav).getByRole('heading', { name })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: 'Payment methods' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(within(nav).getByRole('button', { name: 'Notifications' }))
    expect(screen.getByRole('heading', { name: 'Notifications', exact: true })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('?tab=notifications&from=invoice')
  })
  it('opens a deep-linked section and returns to the mobile settings list', () => {
    mount()
    expect(screen.getByRole('heading', { name: 'Saved card fixture' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Account sections' })
    expect(nav).toHaveClass('hidden', 'md:block')
    fireEvent.click(screen.getByRole('button', { name: '← All settings' }))
    expect(nav).not.toHaveClass('hidden')
    fireEvent.click(within(nav).getByRole('button', { name: 'Payment methods' }))
    expect(nav).toHaveClass('hidden')
  })
  it('follows URL navigation without a stale selected section', () => {
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'External navigation' }))
    expect(screen.getByRole('heading', { name: 'Notifications', exact: true })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Saved card fixture' })).not.toBeInTheDocument()
  })
  it('falls back to Profile for an unknown section and starts with the mobile list', () => {
    mount('?tab=unknown')
    const nav = screen.getByRole('navigation', { name: 'Account sections' })
    expect(within(nav).getByRole('button', { name: 'Profile' })).toHaveAttribute('aria-current', 'page')
    expect(nav).not.toHaveClass('hidden')
  })
})
