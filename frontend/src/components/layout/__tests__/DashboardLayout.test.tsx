import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardLayout from '../DashboardLayout'
import { useAuthStore } from '../../../stores/authStore'
import { garageOwnerSession } from '../../../test-fixtures/db035/staffSession'

const shellState = vi.hoisted(() => ({
  presentationVariant: 'new' as 'new' | 'legacy',
  unreadCount: 0,
  appearance: {
    accent: 'cyan',
    font_family: 'geist',
    font_size: 'small',
    density: 'default',
    notification_position: 'bottom_right',
    mode: 'light',
  },
}))

vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({
    presentationVariant: shellState.presentationVariant,
    accentColors: { 400: '#22d3ee', 500: '#06b6d4', 600: '#0891b2' },
    appearance: shellState.appearance,
  }),
}))
vi.mock('../../../hooks/useTenantBranding', () => ({
  default: () => ({ data: { name: 'Truck Pit Stop Wisconsin', logo_url: null, state: 'WI' } }),
}))
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: { unread_count_staff: shellState.unreadCount } }),
}))
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
      <LocationStateProbe />
    </MemoryRouter>,
  )
}

function LocationStateProbe() {
  const location = useLocation()
  return <output data-testid="dashboard-location-state">{JSON.stringify({ pathname: location.pathname, search: location.search, state: location.state })}</output>
}

describe('DB-035 authenticated staff shell', () => {
  beforeEach(() => {
    window.localStorage.clear()
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    })
    shellState.presentationVariant = 'new'
    shellState.unreadCount = 0
    shellState.appearance = {
      accent: 'cyan',
      font_family: 'geist',
      font_size: 'small',
      density: 'default',
      notification_position: 'bottom_right',
      mode: 'light',
    }
    useAuthStore.setState({
      user: { ...garageOwnerSession, messaging_enabled: true } as never,
      isAuthenticated: true,
      authProvider: 'legacy',
      authSessionEpoch: 4,
      logoutInProgress: false,
    })
  })

  it('expands and collapses the staff rail with accessible persisted controls', async () => {
    window.localStorage.setItem('db-staff-rail-expanded', '0')
    const { unmount } = renderShell()

    const shell = document.querySelector('.db-staff-shell') as HTMLElement
    const expandRail = screen.getByRole('button', { name: 'Expand navigation rail' })
    expect(shell).toHaveAttribute('data-rail-expanded', 'false')
    expect(expandRail).toHaveAttribute('aria-expanded', 'false')
    expect(expandRail).toHaveAttribute('aria-controls', 'db-staff-primary-navigation')

    fireEvent.click(expandRail)

    const collapseRail = screen.getByRole('button', { name: 'Collapse navigation rail' })
    expect(shell).toHaveAttribute('data-rail-expanded', 'true')
    expect(collapseRail).toHaveAttribute('aria-expanded', 'true')
    expect(window.localStorage.getItem('db-staff-rail-expanded')).toBe('1')

    unmount()
    renderShell()
    await screen.findByText('Dashboard surface')
    expect(document.querySelector('.db-staff-shell')).toHaveAttribute('data-rail-expanded', 'true')
    expect(screen.getByRole('button', { name: 'Collapse navigation rail' })).toBeInTheDocument()
  })

  it('keeps appearance ownership on the shell across layout rerenders', () => {
    const { rerender } = renderShell()
    const shell = document.querySelector('.db-staff-shell') as HTMLElement

    expect(shell).toHaveAttribute('data-appearance-mode', 'light')
    expect(shell).toHaveAttribute('data-appearance-density', 'default')
    expect(shell).toHaveAttribute('data-appearance-font-size', 'small')

    shellState.appearance = {
      ...shellState.appearance,
      mode: 'dark',
      density: 'comfortable',
      font_size: 'large',
    }
    rerender(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard/*" element={<DashboardLayout />} />
        </Routes>
        <LocationStateProbe />
      </MemoryRouter>,
    )

    expect(shell).toHaveAttribute('data-appearance-mode', 'dark')
    expect(shell).toHaveAttribute('data-appearance-density', 'comfortable')
    expect(shell).toHaveAttribute('data-appearance-font-size', 'large')
  })

  it('keeps the full owner identity available in the expanded account area', async () => {
    window.localStorage.setItem('db-staff-rail-expanded', '1')
    useAuthStore.setState({
      user: {
        ...garageOwnerSession,
        first_name: 'Maximilian',
        last_name: 'Montgomery-Fields',
      } as never,
    })

    renderShell()
    await screen.findByText('Dashboard surface')

    const account = screen.getByLabelText('Account')
    expect(within(account).getByRole('link', {
      name: 'Open profile settings for Maximilian Montgomery-Fields',
    })).toBeInTheDocument()
    expect(within(account).getByText('Maximilian Montgomery-Fields')).toBeInTheDocument()
  })

  it('uses the compact rail at iPad widths while preserving the desktop preference', () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    })
    window.localStorage.setItem('db-staff-rail-expanded', '1')

    renderShell()

    expect(document.querySelector('.db-staff-shell')).toHaveAttribute('data-rail-expanded', 'false')
    expect(screen.queryByRole('button', { name: /navigation rail/i })).not.toBeInTheDocument()
    expect(window.localStorage.getItem('db-staff-rail-expanded')).toBe('1')
  })

  it('renders DieselBridge first and keeps tenant identity subordinate in the new shell', async () => {
    renderShell()
    await screen.findByText('Dashboard surface')

    const shell = document.querySelector('.db-staff-shell')
    expect(shell).toHaveClass('db-presentation-new')
    expect(shell).toHaveAttribute('data-presentation', 'new')
    expect(screen.getByRole('link', { name: 'DieselBridge Shop Work' })).toHaveAttribute('href', '/dashboard')
    expect(shell).toHaveAttribute('data-surface', 'dashboard')
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
    expect(screen.getByText('Truck Pit Stop Wisconsin', { selector: '.db-workspace-context__fallback' })).toBeInTheDocument()
    expect(document.querySelector('.db-workspace-context__name')).not.toBeInTheDocument()
    const productBrand = screen.getByRole('link', { name: 'DieselBridge Shop Work' })
    const brandLockup = productBrand.closest('.db-brand-lockup')
    expect(brandLockup).toContainElement(screen.getByLabelText('Active shop: Truck Pit Stop Wisconsin'))
    const endorsementRow = brandLockup?.querySelector('.db-brand-endorsement-row')
    expect(endorsementRow).toContainElement(within(screen.getByLabelText('Active shop: Truck Pit Stop Wisconsin')).getByText('WI'))
    expect(endorsementRow).toContainElement(productBrand)
    expect(within(endorsementRow as HTMLElement).getByText('Powered by')).toBeInTheDocument()
    expect(screen.getByText('Truck Pit Stop Wisconsin', { selector: '.db-workspace-context__fallback' }))
      .toHaveClass('db-compact-identity-step--tenant')
    expect(within(endorsementRow as HTMLElement).getByText('WI'))
      .toHaveClass('db-compact-identity-step--state')
    expect(endorsementRow?.querySelector('.db-compact-identity-step--endorsement')).toContainElement(productBrand)
    expect(productBrand.querySelector('.db-wordmark--animated.db-wordmark--type-only')).toHaveTextContent('DieselBridge')
    expect(productBrand.querySelector('.db-wordmark__bridge')).not.toBeInTheDocument()
    expect(productBrand.querySelector('.db-product-brand__compact-mark')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Active shop: Truck Pit Stop Wisconsin')).getByText('WI')).toBeInTheDocument()
    const accountArea = screen.getByLabelText('Account')
    expect(within(accountArea).getByRole('link', { name: 'Open profile settings for Alex Rivera' })).toHaveAttribute('href', '/dashboard/settings')
    expect(screen.getByText('Dashboard surface')).toBeInTheDocument()
  })

  it('uses Shop Work for every new-presentation navigation form while preserving /dashboard', async () => {
    renderShell('/dashboard/repair-orders')
    await screen.findByText('Repair Orders surface')

    const desktop = document.querySelector('.db-staff-primary-nav') as HTMLElement
    const primaryLinks = Array.from(desktop.querySelectorAll<HTMLAnchorElement>('.db-staff-primary-nav__link'))
    expect(primaryLinks.map(link => link.textContent?.trim())).toEqual([
      'Shop Work', 'Repair Orders', 'Customers', 'My Shop',
    ])
    expect(within(desktop).getByRole('link', { name: 'Shop Work' })).toHaveAttribute('href', '/dashboard')
    expect(within(desktop).getByRole('link', { name: 'Repair Orders' })).toHaveAttribute('href', '/dashboard/repair-orders')
    expect(within(desktop).getByRole('link', { name: 'Repair Orders' })).toHaveAttribute('aria-current', 'page')
    expect(within(desktop).getByText('Manage shop')).toBeInTheDocument()
    expect(within(desktop).getByRole('link', { name: 'Open Messages' })).toHaveAttribute('href', '/dashboard/messages')
    expect(within(desktop).getByRole('link', { name: /Open profile settings/ })).toHaveAttribute('href', '/dashboard/settings')
    const mobile = screen.getByLabelText('Mobile navigation')
    expect(within(mobile).getByRole('link', { name: 'Shop Work' })).toHaveAttribute('href', '/dashboard')
    expect(within(mobile).getByRole('link', { name: 'Orders' })).toHaveAttribute('href', '/dashboard/repair-orders')
    expect(within(mobile).getByRole('link', { name: 'Customers' })).toHaveAttribute('href', '/dashboard/customers')
    expect(within(mobile).getByRole('button', { name: 'More' })).toBeInTheDocument()
    expect(screen.getByText('Shop Work', { selector: '.db-breadcrumb a' })).toBeInTheDocument()
    const dashboardLinks = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href="/dashboard"]'))
    expect(dashboardLinks).toHaveLength(4)
    expect(dashboardLinks.every(link => !['Dashboard', 'Home'].includes(link.textContent?.trim() || ''))).toBe(true)
    expect(screen.queryByRole('link', { name: 'Invoices' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Vehicle History' })).not.toBeInTheDocument()
    expect(screen.getByText('Repair Orders surface')).toBeInTheDocument()
  })

  it('keeps Messages as the account-adjacent utility and preserves its unread affordance', async () => {
    shellState.unreadCount = 3
    renderShell('/dashboard/messages')
    await screen.findByText('Messages surface')

    const desktop = document.querySelector('.db-staff-primary-nav') as HTMLElement
    expect(desktop.querySelector('.db-staff-primary-nav__link[href="/dashboard/messages"]')).not.toBeInTheDocument()
    const utilityInbox = within(desktop).getByRole('link', { name: 'Open Messages, 3 unread' })
    expect(utilityInbox).toHaveAttribute('href', '/dashboard/messages')
    expect(utilityInbox).toHaveAttribute('aria-current', 'page')
    expect(within(utilityInbox).getByText('3')).toBeInTheDocument()

    const mobile = screen.getByLabelText('Mobile navigation')
    expect(mobile.querySelector('button[aria-controls="mobile-secondary-navigation"]')).toHaveAttribute('aria-expanded', 'true')
  })

  it('returns a Repair Orders queue launch to Shop Work with the canonical lane context', async () => {
    renderShell('/dashboard/repair-orders?selected=real-order-id&queue=needs_action')
    await screen.findByText('Repair Orders surface')

    fireEvent.click(screen.getByText('Shop Work', { selector: '.db-breadcrumb a' }))

    expect(screen.getByTestId('dashboard-location-state')).toHaveTextContent('"pathname":"/dashboard"')
    expect(screen.getByTestId('dashboard-location-state')).toHaveTextContent('"shopWorkQueue":"needs_action"')
  })

  it('preserves the legacy shell as the immediate presentation rollback', async () => {
    shellState.presentationVariant = 'legacy'
    renderShell('/dashboard/repair-orders')
    await screen.findByText('Repair Orders surface')

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
    expect(screen.queryByRole('button', { name: /navigation rail/i })).not.toBeInTheDocument()
    const legacyLinks = Array.from(desktop.querySelectorAll<HTMLAnchorElement>('.db-staff-primary-nav__link'))
    expect(legacyLinks.map(link => link.textContent?.trim())).toEqual([
      'Dashboard', 'Customers', 'Repair Orders', 'Messages', 'My Shop',
    ])
    expect(desktop.querySelector('.db-staff-nav__utility')).not.toBeInTheDocument()
  })
})
