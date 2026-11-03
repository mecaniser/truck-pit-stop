import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from '../App'
import { useAuthStore } from '../stores/authStore'
import { garageOwnerSession } from '../test-fixtures/db035/staffSession'
const apiMock = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }))
vi.mock('../lib/api', () => ({ default: apiMock }))
// A sentinel marks the real App's provider boundary, without duplicating its guard.
vi.mock('../contexts/ThemeContext', () => ({ ThemeProvider: () => <div>PRIVATE PROVIDERS</div>, useTheme: () => ({}) }))
beforeEach(() => { apiMock.post.mockReset(); useAuthStore.setState({ user: { ...garageOwnerSession }, isAuthenticated: true, logoutInProgress: false, authSessionEpoch: 1, authProvider: 'legacy' }) })
afterEach(() => { cleanup(); useAuthStore.getState().clearSession() })
it.each(['garage_owner', 'customer', 'fleet_manager', 'driver'] as const)('mounts no private provider during pending %s logout', role => {
 useAuthStore.setState({ user: { ...garageOwnerSession, role }, logoutInProgress: true })
 render(<App />)
 expect(screen.queryByText('PRIVATE PROVIDERS')).not.toBeInTheDocument()
 expect(screen.getByRole('status')).toHaveTextContent('Signing out…')
})
it('unmounts the provider tree synchronously for real slow logout and remounts after completion', async () => {
 let finish!: () => void
 apiMock.post.mockImplementation(() => new Promise<void>(resolve => { finish = resolve }))
 render(<App />); expect(screen.getByText('PRIVATE PROVIDERS')).toBeInTheDocument()
 let logout!: Promise<void>
 act(() => { logout = useAuthStore.getState().logout() })
 expect(useAuthStore.getState().user).not.toBeNull()
 expect(screen.queryByText('PRIVATE PROVIDERS')).not.toBeInTheDocument()
 expect(screen.getByRole('status')).toHaveTextContent('Signing out…')
 await act(async () => { finish(); await logout })
 expect(screen.queryByText('Signing out…')).not.toBeInTheDocument()
})
it('keeps the new tenant when an older logout completes late', async () => {
 let finish!: () => void
 apiMock.post.mockImplementation(() => new Promise<void>(resolve => { finish = resolve }))
 render(<App />); let logout!: Promise<void>
 act(() => { logout = useAuthStore.getState().logout() })
 act(() => useAuthStore.getState().establishCookieSession({ ...garageOwnerSession, id: 'owner-b', tenant_id: 'tenant-b' }))
 expect(screen.getByText('PRIVATE PROVIDERS')).toBeInTheDocument()
 await act(async () => { finish(); await logout })
 expect(useAuthStore.getState().user?.tenant_id).toBe('tenant-b')
 expect(screen.getByText('PRIVATE PROVIDERS')).toBeInTheDocument()
})
