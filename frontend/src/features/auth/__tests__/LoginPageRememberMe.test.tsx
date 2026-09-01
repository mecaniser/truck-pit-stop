import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import LoginPage from '../LoginPage'
import { updateRememberedLogin } from '../../../lib/rememberedLogin'

const mockPost = vi.fn()
const mockGet = vi.fn()
const mockNavigate = vi.fn()
const authState: { isAuthenticated: boolean; user: unknown; login: () => void } = {
  isAuthenticated: false,
  user: null,
  login: vi.fn(),
}

vi.mock('../../../lib/api', () => ({
  default: {
    post: (...args: unknown[]) => mockPost(...args),
    get: (...args: unknown[]) => mockGet(...args),
    defaults: { headers: { common: {} } },
  },
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('../../../stores/authStore', () => ({
  useAuthStore: () => authState,
}))

function renderLogin(path = '/login') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LoginPage />
    </MemoryRouter>
  )
}

describe('LoginPage "Remember me"', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    authState.isAuthenticated = false
    authState.user = null
  })

  afterEach(() => {
    window.localStorage.clear()
  })

  it('prefills the email and checks the box when a remembered login exists', () => {
    updateRememberedLogin('owner@example.com', true)
    renderLogin()

    expect((document.getElementById('email') as HTMLInputElement).value).toBe('owner@example.com')
    const checkbox = screen.getByRole('checkbox', { name: /remember me/i }) as HTMLInputElement
    expect(checkbox.checked).toBe(true)
  })

  it('persists the email after a successful login with the box checked', async () => {
    mockPost.mockResolvedValueOnce({ data: { access_token: 'tok', refresh_token: 'ref' } })
    mockGet.mockResolvedValueOnce({ data: { id: 'u-1', role: 'garage_owner', email: 'a@b.com', first_name: 'A', last_name: 'B' } })

    renderLogin()
    const user = userEvent.setup()
    await user.type(document.getElementById('email') as HTMLInputElement, 'owner@example.com')
    await user.type(document.getElementById('password') as HTMLInputElement, 'MyStr0ng@Pass!')
    await user.click(screen.getByRole('checkbox', { name: /remember me/i }))
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(window.localStorage.getItem('db.login.rememberedEmail')).toBe('owner@example.com')
      expect(window.localStorage.getItem('db.login.rememberMe')).toBe('1')
    })
  })

  it('clears a remembered email when logging in with the box unchecked', async () => {
    updateRememberedLogin('old@example.com', true)
    mockPost.mockResolvedValueOnce({ data: { access_token: 'tok', refresh_token: 'ref' } })
    mockGet.mockResolvedValueOnce({ data: { id: 'u-1', role: 'garage_owner', email: 'a@b.com', first_name: 'A', last_name: 'B' } })

    renderLogin()
    const user = userEvent.setup()
    const emailInput = document.getElementById('email') as HTMLInputElement
    await user.clear(emailInput)
    await user.type(emailInput, 'new@example.com')
    await user.type(document.getElementById('password') as HTMLInputElement, 'MyStr0ng@Pass!')
    // leave "remember me" unchecked (it was prefilled checked, so uncheck it)
    await user.click(screen.getByRole('checkbox', { name: /remember me/i }))
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(window.localStorage.getItem('db.login.rememberedEmail')).toBeNull()
      expect(window.localStorage.getItem('db.login.rememberMe')).toBeNull()
    })
  })

  it('auto-redirects an already-authenticated visitor away from /login', async () => {
    authState.isAuthenticated = true
    authState.user = { role: 'garage_owner' }
    renderLogin('/login')

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true })
    })
  })

  it('does NOT auto-redirect when a re-auth reason is present', async () => {
    authState.isAuthenticated = true
    authState.user = { role: 'garage_owner' }
    renderLogin('/login?reason=workos_session_expired')

    // Give the effect a tick.
    await new Promise((r) => setTimeout(r, 0))
    expect(mockNavigate).not.toHaveBeenCalled()
  })
})
