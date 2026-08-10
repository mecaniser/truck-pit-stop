import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import LoginPage from '../LoginPage'

const mockPost = vi.fn()
const mockGet = vi.fn()
const mockNavigate = vi.fn()

vi.mock('../../../lib/api', () => ({
  default: {
    post: (...args: unknown[]) => mockPost(...args),
    get: (...args: unknown[]) => mockGet(...args),
    defaults: { headers: { common: {} } },
  },
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('../../../stores/authStore', () => ({
  useAuthStore: () => ({
    login: vi.fn(),
  }),
}))

function renderLogin(path = '/login') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LoginPage />
    </MemoryRouter>
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function getEmailInput() {
    return document.getElementById('email') as HTMLInputElement
  }
  function getPasswordInput() {
    return document.getElementById('password') as HTMLInputElement
  }

  it('renders email and password fields', () => {
    renderLogin()
    expect(getEmailInput()).toBeInTheDocument()
    expect(getPasswordInput()).toBeInTheDocument()
  })

  it('renders sign in button', () => {
    renderLogin()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /driver portal/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /organization sign-in/i })).toBeInTheDocument()
  })

  it('shows organization sign-in only for an explicitly selected garage', () => {
    renderLogin('/login?tenant_id=tenant-1&return_to=%2Fdashboard')

    expect(screen.getByRole('button', { name: /organization sign-in/i })).toBeInTheDocument()
  })

  it('shows validation errors on empty submit', async () => {
    renderLogin()
    const user = userEvent.setup()

    await user.clear(getEmailInput())
    await user.clear(getPasswordInput())
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/email is required/i)).toBeInTheDocument()
    })
  })

  it('calls API on valid submit', async () => {
    mockPost.mockResolvedValueOnce({
      data: { access_token: 'tok', refresh_token: 'ref' },
    })
    mockGet.mockResolvedValueOnce({
      data: { id: 'u-1', role: 'garage_owner', email: 'a@b.com', first_name: 'A', last_name: 'B' },
    })

    renderLogin()
    const user = userEvent.setup()

    await user.clear(getEmailInput())
    await user.clear(getPasswordInput())
    await user.type(getEmailInput(), 'test@example.com')
    await user.type(getPasswordInput(), 'MyStr0ng@Pass!')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/auth/login', expect.objectContaining({
        email: 'test@example.com',
      }))
    })
  })

  it('displays error message on failed login', async () => {
    mockPost.mockRejectedValueOnce({
      response: { data: { detail: 'Incorrect email or password' } },
    })

    renderLogin()
    const user = userEvent.setup()

    await user.clear(getEmailInput())
    await user.clear(getPasswordInput())
    await user.type(getEmailInput(), 'test@example.com')
    await user.type(getPasswordInput(), 'WrongPass1@x')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/incorrect email or password/i)).toBeInTheDocument()
    })
  })
})
