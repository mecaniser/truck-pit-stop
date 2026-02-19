import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

// Must mock api before importing App (which transitively imports authStore -> api)
vi.mock('../lib/api', () => ({
  default: {
    post: vi.fn().mockResolvedValue({}),
    get: vi.fn().mockResolvedValue({}),
    defaults: { headers: { common: {} } },
  },
}))

// We re-implement the route guards inline to test them in isolation
// (avoids importing the entire App component tree)
function StaffRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <div>REDIRECT_LOGIN</div>
  if (user?.role === 'customer') return <div>REDIRECT_PORTAL</div>
  if (user?.role === 'mechanic') return <div>REDIRECT_MECHANIC</div>
  return <>{children}</>
}

function CustomerRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <div>REDIRECT_LOGIN</div>
  if (user?.role !== 'customer') return <div>REDIRECT_DASHBOARD</div>
  return <>{children}</>
}

function MechanicRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <div>REDIRECT_LOGIN</div>
  if (user?.role !== 'mechanic') return <div>REDIRECT_DASHBOARD</div>
  return <>{children}</>
}

const staffUser = {
  id: 'u-1',
  email: 'staff@garage.com',
  first_name: 'Staff',
  last_name: 'User',
  phone: null,
  role: 'garage_owner' as const,
  is_active: true,
  tenant_id: 't-1',
  customer_id: null,
}

const customerUser = { ...staffUser, id: 'u-2', role: 'customer' as const, customer_id: 'c-1' }
const mechanicUser = { ...staffUser, id: 'u-3', role: 'mechanic' as const }

describe('StaffRoute', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, token: null, refreshToken: null, isAuthenticated: false })
  })

  it('redirects to login when unauthenticated', () => {
    render(
      <MemoryRouter>
        <StaffRoute><div>Dashboard</div></StaffRoute>
      </MemoryRouter>
    )
    expect(screen.getByText('REDIRECT_LOGIN')).toBeInTheDocument()
  })

  it('renders children for staff users', () => {
    useAuthStore.setState({ user: staffUser, token: 'tok', isAuthenticated: true })
    render(
      <MemoryRouter>
        <StaffRoute><div>Dashboard</div></StaffRoute>
      </MemoryRouter>
    )
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('redirects customers to portal', () => {
    useAuthStore.setState({ user: customerUser, token: 'tok', isAuthenticated: true })
    render(
      <MemoryRouter>
        <StaffRoute><div>Dashboard</div></StaffRoute>
      </MemoryRouter>
    )
    expect(screen.getByText('REDIRECT_PORTAL')).toBeInTheDocument()
  })

  it('redirects mechanics to mechanic portal', () => {
    useAuthStore.setState({ user: mechanicUser, token: 'tok', isAuthenticated: true })
    render(
      <MemoryRouter>
        <StaffRoute><div>Dashboard</div></StaffRoute>
      </MemoryRouter>
    )
    expect(screen.getByText('REDIRECT_MECHANIC')).toBeInTheDocument()
  })
})

describe('CustomerRoute', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, token: null, refreshToken: null, isAuthenticated: false })
  })

  it('redirects to login when unauthenticated', () => {
    render(
      <MemoryRouter>
        <CustomerRoute><div>Portal</div></CustomerRoute>
      </MemoryRouter>
    )
    expect(screen.getByText('REDIRECT_LOGIN')).toBeInTheDocument()
  })

  it('renders children for customer users', () => {
    useAuthStore.setState({ user: customerUser, token: 'tok', isAuthenticated: true })
    render(
      <MemoryRouter>
        <CustomerRoute><div>Portal</div></CustomerRoute>
      </MemoryRouter>
    )
    expect(screen.getByText('Portal')).toBeInTheDocument()
  })

  it('redirects non-customers to dashboard', () => {
    useAuthStore.setState({ user: staffUser, token: 'tok', isAuthenticated: true })
    render(
      <MemoryRouter>
        <CustomerRoute><div>Portal</div></CustomerRoute>
      </MemoryRouter>
    )
    expect(screen.getByText('REDIRECT_DASHBOARD')).toBeInTheDocument()
  })
})

describe('MechanicRoute', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, token: null, refreshToken: null, isAuthenticated: false })
  })

  it('redirects to login when unauthenticated', () => {
    render(
      <MemoryRouter>
        <MechanicRoute><div>Timer</div></MechanicRoute>
      </MemoryRouter>
    )
    expect(screen.getByText('REDIRECT_LOGIN')).toBeInTheDocument()
  })

  it('renders children for mechanic users', () => {
    useAuthStore.setState({ user: mechanicUser, token: 'tok', isAuthenticated: true })
    render(
      <MemoryRouter>
        <MechanicRoute><div>Timer</div></MechanicRoute>
      </MemoryRouter>
    )
    expect(screen.getByText('Timer')).toBeInTheDocument()
  })
})
