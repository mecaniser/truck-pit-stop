import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardLayout from '../DashboardLayout'
import { useAuthStore } from '../../../stores/authStore'
import { garageOwnerSession } from '../../../test-fixtures/db035/staffSession'

const shellState = vi.hoisted(() => ({ presentationVariant: 'new' as 'new' | 'legacy' }))

vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({
    presentationVariant: shellState.presentationVariant,
    accentColors: { 400: '#22d3ee', 500: '#06b6d4', 600: '#0891b2' },
  }),
}))
vi.mock('../../../hooks/useTenantBranding', () => ({
  default: () => ({ data: { name: 'Truck Pit Stop Wisconsin', logo_url: null, state: 'WI' } }),
}))
vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: { unread_count_staff: 0 } }) }))
vi.mock('../../../features/customers/CustomersPage', () => ({ default: () => <h1>Customers surface</h1> }))
vi.mock('../../../features/repair-orders/RepairOrdersPage', () => ({ default: () => <h1>Repair Orders surface</h1> }))
vi.mock('../../../features/garage/MyGaragePage', () => ({ default: () => <h1>My Shop surface</h1> }))
vi.mock('../../../features/dashboard/DashboardHome', () => ({ default: () => <h1>Dashboard surface</h1> }))
vi.mock('../../../features/dashboard/UnifiedSettingsPage', () => ({ default: () => <h1>Settings surface</h1> }))
vi.mock('../../../features/platform-admin/PlatformDashboard', () => ({ default: () => <h1>Platform surface</h1> }))
vi.mock('../../../features/platform-admin/GaragesPage', () => ({ default: () => null }))
vi.mock('../../../features/platform-admin/GarageAnalyticsPage', () => ({ default: () => null }))
vi.mock('../../../features/platform-admin/PlatformAnalyticsPage', () => ({ default: () => null }))
vi.mock('../../../features/platform-admin/PendingEnrollmentsPage', () => ({ default: () => null }))
vi.mock('../../../features/platform-admin/PaymentControlCenter', () => ({ default: () => null }))
vi.mock('../../../features/messages/MessagesInboxPage', () => ({ default: () => <h1>Messages surface</h1> }))
vi.mock('../../../features/dashboard/MechanicsBoardPage', () => ({ default: () => null }))
vi.mock('../../../features/dashboard/MechanicBoardDetailPage', () => ({ default: () => null }))

function renderShell(path = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/dashboard/*" element={<DashboardLayout />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('DB-035 authenticated staff shell', () => {
  beforeEach(() => {
    shellState.presentationVariant = 'new'
    useAuthStore.setState({
      user: { ...garageOwnerSession, messaging_enabled: true } as never,
      isAuthenticated: true,
      authProvider: 'legacy',
      authSessionEpoch: 4,
      logoutInProgress: false,
    })
  })

  it('renders DieselBridge first and keeps tenant identity subordinate in the new shell', () => {
    renderShell()

    const shell = document.querySelector('.db-staff-shell')
    expect(shell).toHaveClass('db-presentation-new')
    expect(shell).toHaveAttribute('data-presentation', 'new')
    expect(screen.getByRole('link', { name: 'DieselBridge Shop Work' })).toHaveAttribute('href', '/dashboard')
    const desktopShopWork = within(document.querySelector('.db-staff-primary-nav') as HTMLElement)
      .getByRole('link', { name: 'Shop Work' })
    const mobileShopWork = within(screen.getByLabelText('Mobile navigation'))
      .getByRole('link', { name: 'Shop Work' })
    expect(desktopShopWork).toHaveAttribute('href', '/dashboard')
    expect(desktopShopWork).toHaveAttribute('aria-current', 'page')
    expect(mobileShopWork).toHaveAttribute('href', '/dashboard')
    expect(mobileShopWork).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Home' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Active shop: Truck Pit Stop Wisconsin')).toHaveTextContent('Truck Pit Stop Wisconsin')
    const productBrand = screen.getByRole('link', { name: 'DieselBridge Shop Work' })
    expect(productBrand.querySelector('.db-wordmark--animated.db-wordmark--type-only')).toHaveTextContent('DieselBridge')
    expect(productBrand.querySelector('.db-wordmark__bridge')).not.toBeInTheDocument()
    expect(productBrand.querySelector('.db-product-brand__compact-mark')).toBeInTheDocument()
    expect(document.querySelector('.db-workspace-context__state')).toHaveTextContent('WI')
    const accountArea = screen.getByLabelText('Account')
    expect(within(accountArea).getByRole('link', { name: 'Open profile settings for Alex Rivera' })).toHaveAttribute('href', '/dashboard/settings')
    expect(screen.getByText('Dashboard surface')).toBeInTheDocument()
  })

  it('uses Shop Work for every new-presentation navigation form while preserving /dashboard', () => {
    renderShell('/dashboard/repair-orders')

    const desktop = document.querySelector('.db-staff-primary-nav') as HTMLElement
    const links = within(desktop).getAllByRole('link')
    expect(links.slice(0, 5).map(link => link.textContent?.trim())).toEqual([
      'Shop Work', 'Customers', 'Repair Orders', 'Messages', 'My Shop',
    ])
    expect(within(desktop).getByRole('link', { name: 'Shop Work' })).toHaveAttribute('href', '/dashboard')
    expect(within(desktop).getByRole('link', { name: 'Repair Orders' })).toHaveAttribute('href', '/dashboard/repair-orders')
    expect(within(desktop).getByRole('link', { name: 'Repair Orders' })).toHaveAttribute('aria-current', 'page')
    expect(within(desktop).getByRole('link', { name: /Open profile settings/ })).toHaveAttribute('href', '/dashboard/settings')
    const mobile = screen.getByLabelText('Mobile navigation')
    expect(within(mobile).getByRole('link', { name: 'Shop Work' })).toHaveAttribute('href', '/dashboard')
    expect(screen.getByText('Shop Work', { selector: '.db-breadcrumb a' })).toBeInTheDocument()
    const dashboardLinks = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href="/dashboard"]'))
    expect(dashboardLinks).toHaveLength(4)
    expect(dashboardLinks.every(link => !['Dashboard', 'Home'].includes(link.textContent?.trim() || ''))).toBe(true)
    expect(screen.queryByRole('link', { name: 'Invoices' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Vehicle History' })).not.toBeInTheDocument()
    expect(screen.getByText('Repair Orders surface')).toBeInTheDocument()
  })

  it('preserves the legacy shell as the immediate presentation rollback', () => {
    shellState.presentationVariant = 'legacy'
    renderShell('/dashboard/repair-orders')

    const shell = document.querySelector('.db-staff-shell')
    expect(shell).toHaveClass('db-presentation-legacy')
    expect(shell).toHaveAttribute('data-presentation', 'legacy')
    expect(screen.getByRole('link', { name: 'Truck Pit Stop Wisconsin dashboard' })).toBeInTheDocument()
    const desktop = document.querySelector('.db-staff-primary-nav') as HTMLElement
    expect(within(desktop).getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/dashboard')
    expect(within(screen.getByLabelText('Mobile navigation')).getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/dashboard')
    expect(screen.getByText('Dashboard', { selector: '.db-breadcrumb a' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Diesel Bridge Network' })).toBeInTheDocument()
    expect(screen.queryByText('DieselBridge', { selector: '.db-product-brand__name' })).not.toBeInTheDocument()
  })
})
