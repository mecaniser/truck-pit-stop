import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { lazy, Suspense, type MouseEvent as ReactMouseEvent, type TouchEvent, useEffect, useRef, useState } from 'react'
import { useAuthStore } from '../../stores/authStore'
import { Home, Users, ClipboardList, Building2, User, LayoutGrid, BarChart3, UserCheck, Crown, MessageSquare, CreditCard, MoreHorizontal, ChevronLeft, ChevronsLeft, ChevronsRight } from 'lucide-react'
import { useTheme } from '../../contexts/ThemeContext'
import api from '@/lib/api'
import type { MessagesUnreadSummary } from '@/types'
import BrandLogo from '../brand/BrandLogo'
import DieselBridgeWordmark from '../brand/DieselBridgeWordmark'
import TenantBrandLogo from '../brand/TenantBrandLogo'
import useTenantBranding from '@/hooks/useTenantBranding'

const STAFF_RAIL_STORAGE_KEY = 'db-staff-rail-expanded'
const CustomersPage = lazy(() => import('@/features/customers/CustomersPage'))
const RepairOrdersPage = lazy(() => import('@/features/repair-orders/RepairOrdersPage'))
const MyGaragePage = lazy(() => import('@/features/garage/MyGaragePage'))
const DashboardHome = lazy(() => import('@/features/dashboard/DashboardHome'))
const UnifiedSettingsPage = lazy(() => import('@/features/dashboard/UnifiedSettingsPage'))
const PlatformDashboard = lazy(() => import('@/features/platform-admin/PlatformDashboard'))
const GaragesPage = lazy(() => import('@/features/platform-admin/GaragesPage'))
const GarageAnalyticsPage = lazy(() => import('@/features/platform-admin/GarageAnalyticsPage'))
const PlatformAnalyticsPage = lazy(() => import('@/features/platform-admin/PlatformAnalyticsPage'))
const PendingEnrollmentsPage = lazy(() => import('@/features/platform-admin/PendingEnrollmentsPage'))
const PaymentControlCenter = lazy(() => import('@/features/platform-admin/PaymentControlCenter'))
const MessagesInboxPage = lazy(() => import('@/features/messages/MessagesInboxPage'))
const MechanicsBoardPage = lazy(() => import('@/features/dashboard/MechanicsBoardPage'))
const MechanicBoardDetailPage = lazy(() => import('@/features/dashboard/MechanicBoardDetailPage'))

function getInitialStaffRailExpanded() {
  const storedPreference = window.localStorage.getItem(STAFF_RAIL_STORAGE_KEY)
  if (storedPreference === '1') return true
  if (storedPreference === '0') return false
  return typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 1280px)').matches
}

function getStaffRailCanExpand() {
  return typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 1280px)').matches
}

export default function DashboardLayout() {
  const { user } = useAuthStore()
  const location = useLocation()
  const [mobileNavPage, setMobileNavPage] = useState<'primary' | 'secondary'>('primary')
  const [staffRailExpanded, setStaffRailExpanded] = useState(getInitialStaffRailExpanded)
  const [staffRailCanExpand, setStaffRailCanExpand] = useState(getStaffRailCanExpand)
  const mobileNavTouchStart = useRef<{ x: number; y: number } | null>(null)
  const suppressMobileNavClick = useRef(false)
  const { accentColors, presentationVariant, appearance } = useTheme()
  // Owner/admin/receptionist/mechanic have messaging by role; other roles
  // (notably fleet managers) need the can_access_messaging grant. Either way,
  // the shop-wide messaging_enabled switch can turn the whole feature off
  // (absent flag = on, so nothing changes until a shop disables it).
  const shopMessagingEnabled = user?.messaging_enabled !== false
  const canAccessMessaging =
    shopMessagingEnabled &&
    (['garage_owner', 'garage_admin', 'receptionist', 'mechanic'].includes(user?.role || '') ||
      Boolean(user?.can_access_messaging))
  const messagesNavLink = { to: '/dashboard/messages', label: 'Messages', mobileLabel: 'Messages', exact: false, icon: MessageSquare }
  const shouldFetchMessagesUnread = Boolean(user && user.role !== 'super_admin' && canAccessMessaging)
  const { data: unreadSummary } = useQuery({
    queryKey: ['messages-unread-summary'],
    queryFn: async () => {
      const { data } = await api.get<MessagesUnreadSummary>('/messages/unread-summary')
      return data
    },
    enabled: shouldFetchMessagesUnread,
    staleTime: 0,
    refetchInterval: 45000,
    refetchIntervalInBackground: true,
  })
  const unreadCount = unreadSummary?.unread_count_staff || 0
  const unreadBadge = unreadCount > 99 ? '99+' : `${unreadCount}`
  const { data: tenantBranding } = useTenantBranding()
  
  // Get the hex color for the current accent
  const accentHex = accentColors[500]

  const isSuperAdmin = user?.role === 'super_admin'
  const dashboardLabel = presentationVariant === 'new' && !isSuperAdmin ? 'Shop Work' : 'Dashboard'
  const dashboardMobileLabel = presentationVariant === 'new' && !isSuperAdmin ? 'Shop Work' : 'Home'
  const isNewStaffPresentation = presentationVariant === 'new' && !isSuperAdmin

  // Different navigation for SUPER_ADMIN (platform management) vs garage staff
  const superAdminNavLinks = [
    { to: '/dashboard', label: 'Dashboard', mobileLabel: 'Home', exact: true, icon: Home },
    { to: '/dashboard/garages', label: 'Shops', mobileLabel: 'Shops', exact: false, icon: LayoutGrid },
    { to: '/dashboard/pending-enrollments', label: 'Enrollments', mobileLabel: 'Enroll', exact: false, icon: UserCheck },
    { to: '/dashboard/analytics', label: 'Analytics', mobileLabel: 'Stats', exact: false, icon: BarChart3 },
    { to: '/dashboard/payments', label: 'Payments', mobileLabel: 'Pay', exact: false, icon: CreditCard },
  ]
  const staffNavLinkByPath = {
    dashboard: { to: '/dashboard', label: dashboardLabel, mobileLabel: dashboardMobileLabel, exact: true, icon: Home },
    customers: { to: '/dashboard/customers', label: 'Customers', mobileLabel: 'Customers', exact: false, icon: Users },
    repairOrders: { to: '/dashboard/repair-orders', label: 'Repair Orders', mobileLabel: 'Orders', exact: false, icon: ClipboardList },
    myShop: { to: '/dashboard/garage', label: 'My Shop', mobileLabel: 'Shop', exact: false, icon: Building2 },
  }
  const legacyStaffNavLinks = [
    staffNavLinkByPath.dashboard,
    staffNavLinkByPath.customers,
    staffNavLinkByPath.repairOrders,
    ...(canAccessMessaging ? [messagesNavLink] : []),
    staffNavLinkByPath.myShop,
  ]
  const newStaffNavLinks = [
    staffNavLinkByPath.dashboard,
    staffNavLinkByPath.repairOrders,
    staffNavLinkByPath.customers,
    ...(canAccessMessaging ? [messagesNavLink] : []),
    staffNavLinkByPath.myShop,
  ]
  const navLinks = user?.role === 'super_admin'
    ? [
        ...superAdminNavLinks,
      ]
    : isNewStaffPresentation
      ? newStaffNavLinks
      : legacyStaffNavLinks
  const operationalNavLinks = isNewStaffPresentation
    ? navLinks.filter((link) => ['/dashboard', '/dashboard/repair-orders', '/dashboard/customers'].includes(link.to))
    : navLinks
  const managementNavLink = isNewStaffPresentation
    ? navLinks.find((link) => link.to === '/dashboard/garage')
    : undefined
  const utilityMessagesLink = isNewStaffPresentation
    ? navLinks.find((link) => link.to === '/dashboard/messages')
    : undefined

  const isActive = (path: string, exact?: boolean) => 
    exact ? location.pathname === path : location.pathname.startsWith(path)

  const preferredMobilePaths = isSuperAdmin
    ? ['/dashboard', '/dashboard/garages', '/dashboard/pending-enrollments', '/dashboard/analytics']
    : isNewStaffPresentation
      ? ['/dashboard', '/dashboard/repair-orders', '/dashboard/customers']
      : ['/dashboard', '/dashboard/customers', '/dashboard/repair-orders', '/dashboard/messages']
  const preferredMobileLinks = preferredMobilePaths
    .map(path => navLinks.find(link => link.to === path))
    .filter((link): link is (typeof navLinks)[number] => Boolean(link))
  const mobilePrimaryLinks = isNewStaffPresentation
    ? preferredMobileLinks
    : [
        ...preferredMobileLinks,
        ...navLinks.filter(link => !preferredMobileLinks.some(primary => primary.to === link.to)),
      ].slice(0, 4)
  const mobileOverflowLinks = navLinks.filter(
    link => !mobilePrimaryLinks.some(primary => primary.to === link.to),
  )
  const isMobileMoreActive =
    location.pathname === '/dashboard/settings' ||
    mobileOverflowLinks.some(link => isActive(link.to, link.exact))

  useEffect(() => {
    setMobileNavPage(isMobileMoreActive ? 'secondary' : 'primary')
  }, [isMobileMoreActive, location.pathname])

  const handleMobileNavTouchStart = (event: TouchEvent<HTMLDivElement>) => {
    const touch = event.touches[0]
    if (!touch) return
    mobileNavTouchStart.current = { x: touch.clientX, y: touch.clientY }
  }

  const handleMobileNavTouchEnd = (event: TouchEvent<HTMLDivElement>) => {
    const start = mobileNavTouchStart.current
    const touch = event.changedTouches[0]
    mobileNavTouchStart.current = null
    if (!start || !touch) return

    const deltaX = touch.clientX - start.x
    const deltaY = touch.clientY - start.y
    if (Math.abs(deltaX) < 36 || Math.abs(deltaX) <= Math.abs(deltaY) * 1.2) return

    suppressMobileNavClick.current = true
    window.setTimeout(() => {
      suppressMobileNavClick.current = false
    }, 350)
    if (deltaX < 0 && mobileNavPage === 'primary') setMobileNavPage('secondary')
    if (deltaX > 0 && mobileNavPage === 'secondary') setMobileNavPage('primary')
  }

  const handleMobileNavClickCapture = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!suppressMobileNavClick.current) return
    suppressMobileNavClick.current = false
    event.preventDefault()
    event.stopPropagation()
  }

  const isOnSubPage = location.pathname !== '/dashboard'
  const repairOrdersQueue = new URLSearchParams(location.search).get('queue')
  const shopWorkQueue = repairOrdersQueue === 'needs_action' || repairOrdersQueue === 'on_floor' || repairOrdersQueue === 'ready_to_close'
    ? repairOrdersQueue
    : null
  const shopWorkBreadcrumbState = presentationVariant === 'new' && location.pathname === '/dashboard/repair-orders' && shopWorkQueue
    ? { shopWorkQueue }
    : undefined
  
  const getCurrentPageLabel = () => {
    if (location.pathname === '/dashboard/settings') return 'Profile Settings'
    if (location.pathname === '/dashboard/mechanics') return 'Technician Board'
    if (location.pathname.startsWith('/dashboard/mechanics/')) return 'Technician Detail'
    if (location.pathname === '/dashboard/customers' || location.pathname.startsWith('/dashboard/customers/')) return 'Customers'
    if (location.pathname === '/dashboard/repair-orders') return 'Repair Orders'
    if (location.pathname === '/dashboard/messages') return 'Messages'
    if (location.pathname === '/dashboard/garage' || location.pathname.startsWith('/dashboard/garage/')) return 'My Shop'
    const current = navLinks.find(link => location.pathname === link.to)
    return current?.label || ''
  }

  const isGarageWorkspaceRoute =
    !isSuperAdmin &&
    (location.pathname === '/dashboard/garage' ||
      location.pathname.startsWith('/dashboard/garage/') ||
      location.pathname === '/dashboard/customers' ||
      location.pathname.startsWith('/dashboard/customers/'))
  const dashboardLogoAlt = isSuperAdmin
    ? 'Diesel Bridge Network'
    : tenantBranding?.name || user?.tenant_name || 'Diesel Bridge Network'
  const dashboardAriaLabel = presentationVariant === 'new'
    ? isSuperAdmin
      ? 'DieselBridge dashboard'
      : 'Powered by DieselBridge — Shop Work'
    : isSuperAdmin
      ? 'Diesel Bridge Network dashboard'
      : `${dashboardLogoAlt} dashboard`
  const profileNameParts = [user?.first_name, user?.last_name].filter(
    (part): part is string => Boolean(part?.trim()),
  )
  const profileDisplayName = profileNameParts.join(' ').trim() || user?.email || 'Profile Settings'
  const profileMonogram = (
    profileNameParts.map((part) => part.charAt(0)).join('') ||
    user?.email?.replace(/[^a-zA-Z0-9]/g, '').slice(0, 2) ||
    'ME'
  ).slice(0, 2).toUpperCase()
  const profileTileBorder = isSuperAdmin ? 'rgba(212, 168, 75, 0.45)' : `${accentHex}55`
  const profileTileGlow = isSuperAdmin ? 'rgba(184, 134, 11, 0.22)' : `${accentHex}26`
  const profileTileInset = isSuperAdmin
    ? 'linear-gradient(180deg, rgba(255,255,255,0.08), rgba(184,134,11,0.08))'
    : `linear-gradient(180deg, ${accentHex}29, rgba(255,255,255,0.04))`

  // Garage users get BlueNoir theme
  const isGarageUser = !isSuperAdmin
  const showStaffRailToggle = presentationVariant === 'new' && isGarageUser
  const isStaffRailExpanded = showStaffRailToggle && staffRailCanExpand && staffRailExpanded

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(min-width: 1280px)')
    const updateRailCapability = () => setStaffRailCanExpand(query.matches)
    updateRailCapability()
    query.addEventListener?.('change', updateRailCapability)
    return () => query.removeEventListener?.('change', updateRailCapability)
  }, [])

  const toggleStaffRail = () => {
    setStaffRailExpanded((expanded) => {
      const nextExpanded = !expanded
      window.localStorage.setItem(STAFF_RAIL_STORAGE_KEY, nextExpanded ? '1' : '0')
      return nextExpanded
    })
  }

  const renderDesktopNavLink = (
    link: (typeof navLinks)[number],
    kind: 'operational' | 'management' = 'operational',
  ) => (
    <Link
      key={link.to}
      to={link.to}
      aria-current={isActive(link.to, link.exact) ? 'page' : undefined}
      title={presentationVariant === 'new' ? link.label : undefined}
      className={`db-staff-primary-nav__link db-staff-primary-nav__link--${kind} text-sm font-medium transition-colors ${
        isActive(link.to, link.exact)
          ? isSuperAdmin
            ? 'text-gold-400 border-b-2 border-gold-500'
            : 'border-b-2'
          : isSuperAdmin
            ? 'text-gray-400 hover:text-gold-400'
            : 'text-gray-400 hover:text-white'
      }`}
      style={!isSuperAdmin && presentationVariant === 'legacy' && isActive(link.to, link.exact) ? { color: accentHex, borderColor: accentHex } : undefined}
    >
      <span className="inline-flex items-center gap-2">
        {presentationVariant === 'new' && <link.icon className="h-4 w-4" aria-hidden="true" />}
        <span className="db-staff-primary-nav__label">{link.label}</span>
        {link.to === '/dashboard/messages' && unreadCount > 0 && (
          <span className="inline-flex min-w-[1.25rem] h-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-[11px] font-semibold leading-none text-white">
            {unreadBadge}
          </span>
        )}
      </span>
    </Link>
  )

  return (
    <div
      className={`db-staff-shell db-presentation-${presentationVariant} h-screen overflow-hidden ${isGarageUser ? 'bg-blueNoir-900' : ''}`}
      data-presentation={presentationVariant}
      data-appearance-mode={appearance.mode}
      data-appearance-density={appearance.density}
      data-appearance-font-size={appearance.font_size}
      data-surface={getCurrentPageLabel().toLowerCase().replace(/\s+/g, '-') || 'dashboard'}
      data-rail-expanded={showStaffRailToggle ? String(isStaffRailExpanded) : undefined}
    >
      <nav className={`db-staff-nav sticky top-0 z-50 ${
        isSuperAdmin 
          ? 'bg-noir-900/95 backdrop-blur-xl border-b border-gold-500/20 shadow-lg shadow-gold-500/5' 
          : 'bg-blueNoir-800/95 backdrop-blur-xl border-b border-white/10 shadow-lg'
      }`}>
        <div className="db-staff-nav__inner max-w-7xl mx-auto px-4">
          <div className="db-staff-nav__layout flex justify-between h-14 sm:h-16">
            {/* Logo */}
            <div className="db-staff-nav__brand-row flex items-center gap-3">
              <div className="db-brand-lockup">
              {!isSuperAdmin && presentationVariant === 'new' && (
                <div className="db-workspace-context" aria-label={`Active shop: ${dashboardLogoAlt}`}>
                  <div className="db-workspace-context__tenant">
                    {tenantBranding?.logo_url ? (
                      <img
                        src={tenantBranding.logo_url}
                        alt=""
                        className="db-workspace-context__logo db-compact-identity-step db-compact-identity-step--tenant h-9 w-auto object-contain"
                      />
                    ) : (
                      <span className="db-workspace-context__fallback db-compact-identity-step db-compact-identity-step--tenant">{dashboardLogoAlt}</span>
                    )}
                    <div className="db-brand-endorsement-row">
                      {tenantBranding?.state && (
                        <span className="db-workspace-context__state db-compact-identity-step db-compact-identity-step--state inline-flex items-center px-2 py-0.5 rounded-full border border-white/10 bg-white/5 text-[11px] font-medium tracking-wide text-gray-300">
                          {tenantBranding.state}
                        </span>
                      )}
                      <div className="db-brand-attribution db-compact-identity-step db-compact-identity-step--endorsement">
                        <span className="db-brand-attribution__label">Powered by</span>
                        <Link to="/dashboard" className="db-product-brand inline-flex items-center py-1" aria-label={dashboardAriaLabel}>
                          <DieselBridgeWordmark animated showBridge={false} />
                          <BrandLogo alt="" variant="admin" className="db-product-brand__compact-mark" />
                        </Link>
                      </div>
                    </div>
                  </div>
                </div>
              )}
              {(isSuperAdmin || presentationVariant !== 'new') && (
                <div className="db-brand-attribution">
                <Link to="/dashboard" className="db-product-brand inline-flex items-center py-1" aria-label={dashboardAriaLabel}>
                  {isSuperAdmin ? (
                    <BrandLogo alt="Diesel Bridge Network" variant="admin" className="h-8 sm:h-10 w-auto" />
                  ) : (
                    <TenantBrandLogo
                      tenantLogoUrl={tenantBranding?.logo_url}
                      tenantName={tenantBranding?.name || user?.tenant_name}
                      fallbackVariant="admin"
                      className="h-8 sm:h-10 w-auto object-contain"
                    />
                  )}
                </Link>
                </div>
              )}
              </div>
              {isSuperAdmin && (
                <span className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-gold-500/10 border border-gold-500/30 rounded-full text-gold-400 text-xs font-medium">
                  <Crown className="w-3 h-3" />
                  Platform Admin
                </span>
              )}
            </div>

            {/* Desktop nav */}
            <div id="db-staff-primary-navigation" className="db-staff-primary-nav hidden md:flex md:items-center md:space-x-6">
              {isNewStaffPresentation ? (
                <>
                  {operationalNavLinks.map((link) => renderDesktopNavLink(link))}
                  {managementNavLink && (
                    <>
                      <span className="db-staff-primary-nav__section-label" aria-hidden="true">Manage shop</span>
                      {renderDesktopNavLink(managementNavLink, 'management')}
                    </>
                  )}
                </>
              ) : (
                navLinks.map((link) => renderDesktopNavLink(link))
              )}
              <div className="db-staff-nav__profile" aria-label="Account">
                {utilityMessagesLink && (
                  <Link
                    to={utilityMessagesLink.to}
                    aria-current={isActive(utilityMessagesLink.to) ? 'page' : undefined}
                    aria-label={`Open Messages${unreadCount > 0 ? `, ${unreadBadge} unread` : ''}`}
                    title={unreadCount > 0 ? `Messages — ${unreadBadge} unread` : 'Messages'}
                    className="db-staff-nav__utility"
                  >
                    <span className="relative inline-flex">
                      <MessageSquare className="h-4 w-4" aria-hidden="true" />
                      {unreadCount > 0 && (
                        <span className="db-staff-nav__utility-badge" aria-hidden="true">{unreadBadge}</span>
                      )}
                    </span>
                    <span className="db-staff-nav__utility-label" aria-hidden="true">Messages</span>
                  </Link>
                )}
                <div className="db-staff-nav__account-controls">
                  <Link
                    to="/dashboard/settings"
                    aria-current={location.pathname === '/dashboard/settings' ? 'page' : undefined}
                    aria-label={`Open profile settings for ${profileDisplayName}`}
                    className={`group relative flex h-11 w-11 items-center justify-center rounded-2xl border bg-white/[0.03] transition-all ${
                    location.pathname === '/dashboard/settings'
                      ? isSuperAdmin
                        ? 'border-gold-500/40 bg-gold-500/10 text-gold-300'
                        : 'bg-white/[0.08] text-white'
                      : isSuperAdmin
                        ? 'border-white/10 text-gray-400 hover:border-gold-500/30 hover:bg-gold-500/10 hover:text-gold-300'
                        : 'border-white/10 text-gray-400 hover:border-white/20 hover:bg-white/[0.06] hover:text-white'
                  }`}
                  style={presentationVariant === 'legacy' ? {
                    color: !isSuperAdmin && location.pathname === '/dashboard/settings' ? accentHex : undefined,
                    borderColor: !isSuperAdmin && location.pathname === '/dashboard/settings' ? profileTileBorder : undefined,
                    boxShadow: `0 10px 24px ${profileTileGlow}`,
                  } : undefined}
                  title={profileDisplayName}
                  >
                    <div
                      className="absolute inset-[3px] rounded-[14px] border border-white/5"
                      style={{ background: profileTileInset }}
                    />
                    <div className="db-staff-nav__profile-monogram relative flex h-full w-full items-center justify-center rounded-[14px]">
                      <span className="text-[11px] font-semibold tracking-[0.18em]">
                        {profileMonogram}
                      </span>
                    </div>
                    {presentationVariant === 'new' && (
                      <span className="db-staff-nav__profile-copy" aria-hidden="true">
                        <strong>{profileDisplayName}</strong>
                        <small>Profile &amp; settings</small>
                      </span>
                    )}
                    <span
                      className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 shadow-[0_0_10px_rgba(52,211,153,0.6)]"
                      style={{ backgroundColor: '#34d399', borderColor: isSuperAdmin ? '#0a0b0d' : '#10151f' }}
                    />
                  </Link>
                  {showStaffRailToggle && staffRailCanExpand && (
                    <button
                      type="button"
                      className="db-staff-nav__rail-toggle"
                      onClick={toggleStaffRail}
                      aria-expanded={isStaffRailExpanded}
                      aria-controls="db-staff-primary-navigation"
                      aria-label={isStaffRailExpanded ? 'Collapse navigation rail' : 'Expand navigation rail'}
                      title={isStaffRailExpanded ? 'Collapse navigation rail' : 'Expand navigation rail'}
                    >
                      {isStaffRailExpanded ? (
                        <ChevronsLeft className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <ChevronsRight className="h-4 w-4" aria-hidden="true" />
                      )}
                    </button>
                  )}
                </div>
              </div>
            </div>

          </div>
        </div>
      </nav>

      <main
        className="db-staff-main px-4 sm:px-6 lg:px-8 py-4 sm:py-6 flex flex-col h-[calc(100vh-3.5rem)] sm:h-[calc(100vh-4rem)] overflow-hidden"
      >
        {/* Breadcrumb - only show on sub-pages */}
        {isOnSubPage && (
          <div className="db-breadcrumb mb-4 flex-shrink-0 flex items-center gap-2 text-sm">
            <Link
              to="/dashboard"
              state={shopWorkBreadcrumbState}
              className="transition-colors flex items-center gap-1 text-gray-400 hover:text-white"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              {dashboardLabel}
            </Link>
            <span className="text-gray-600">/</span>
            <span
              className="font-medium"
              style={{ color: isSuperAdmin ? '#D4A84B' : accentHex }}
            >
              {getCurrentPageLabel()}
            </span>
          </div>
        )}
        <div
          className={`db-staff-content flex-1 min-h-0 flex flex-col scrollbar-dark ${
            isGarageWorkspaceRoute ? 'overflow-y-auto lg:overflow-hidden' : 'overflow-y-auto'
          }`}
        >
          <Suspense fallback={<div className="min-h-24" role="status" aria-live="polite">Loading workspace…</div>}>
          <Routes>
            {/* Platform Admin Routes (SUPER_ADMIN only) */}
            {user?.role === 'super_admin' ? (
              <>
                <Route path="garages" element={<GaragesPage />} />
                <Route path="garages/:garageId/analytics" element={<GarageAnalyticsPage />} />
                <Route path="pending-enrollments" element={<PendingEnrollmentsPage />} />
                <Route path="analytics" element={<PlatformAnalyticsPage />} />
                <Route path="payments" element={<PaymentControlCenter />} />
                <Route path="settings" element={<UnifiedSettingsPage />} />
                <Route path="" element={<PlatformDashboard />} />
              </>
            ) : (
              /* Garage Staff Routes */
              <>
                <Route path="customers" element={<CustomersPage />} />
                <Route path="repair-orders" element={<RepairOrdersPage />} />
                <Route
                  path="messages"
                  element={canAccessMessaging ? <MessagesInboxPage /> : <Navigate to="/dashboard" replace />}
                />
                <Route path="mechanics" element={<MechanicsBoardPage />} />
                <Route path="mechanics/:mechanicId" element={<MechanicBoardDetailPage />} />
                <Route path="garage/*" element={<MyGaragePage />} />
                <Route path="settings" element={<UnifiedSettingsPage />} />
                <Route
                  path=""
                  element={<DashboardHome />}
                />
              </>
            )}
          </Routes>
          </Suspense>
          {/* Spacer so content clears the fixed bottom nav on mobile */}
          <div
            className="db-mobile-nav-spacer md:hidden flex-shrink-0"
            style={{ height: 'calc(4rem + env(safe-area-inset-bottom))' }}
          />
        </div>
      </main>

      {/* Mobile Bottom Navigation */}
      <div className="db-mobile-nav fixed bottom-0 left-0 right-0 z-50 md:hidden">
        <div className={`overflow-hidden pt-2 ${
          isSuperAdmin
            ? 'bg-noir-900/95 backdrop-blur-xl border-t border-gold-500/20'
            : 'bg-blueNoir-800/95 backdrop-blur-xl border-t border-white/10'
        }`}
          style={{ paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom))' }}
          onTouchStart={handleMobileNavTouchStart}
          onTouchEnd={handleMobileNavTouchEnd}
          onClickCapture={handleMobileNavClickCapture}
          aria-label="Mobile navigation"
        >
          <div
            className={`flex w-[200%] transform-gpu transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
              mobileNavPage === 'secondary' ? '-translate-x-1/2' : 'translate-x-0'
            }`}
          >
            <div className="flex w-1/2 shrink-0 justify-around px-2" aria-hidden={mobileNavPage !== 'primary'}>
              {mobilePrimaryLinks.map((link) => {
                const Icon = link.icon
                const isLinkActive = isActive(link.to, link.exact)
                return (
                  <Link
                    key={link.to}
                    to={link.to}
                    aria-current={isLinkActive ? 'page' : undefined}
                    tabIndex={mobileNavPage === 'primary' ? 0 : -1}
                    className={`flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 px-1 ${
                      isLinkActive
                        ? isSuperAdmin ? 'text-gold-400' : ''
                        : isSuperAdmin ? 'text-gray-500 hover:text-gold-400' : 'text-gray-500 hover:text-white'
                    }`}
                    style={!isSuperAdmin && presentationVariant === 'legacy' && isLinkActive ? { color: accentHex } : undefined}
                  >
                    <div className="relative">
                      <Icon className="h-5 w-5" />
                      {link.to === '/dashboard/messages' && unreadCount > 0 && (
                        <span className="absolute -right-2 -top-2 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-none text-white">
                          {unreadBadge}
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] font-medium">{link.mobileLabel}</span>
                  </Link>
                )
              })}
              <button
                type="button"
                onClick={() => setMobileNavPage('secondary')}
                tabIndex={mobileNavPage === 'primary' ? 0 : -1}
                aria-expanded={mobileNavPage === 'secondary'}
                aria-controls="mobile-secondary-navigation"
                className={`flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 px-1 ${
                  isMobileMoreActive
                    ? isSuperAdmin ? 'text-gold-400' : ''
                    : isSuperAdmin ? 'text-gray-500 hover:text-gold-400' : 'text-gray-500 hover:text-white'
                }`}
                style={!isSuperAdmin && presentationVariant === 'legacy' && isMobileMoreActive ? { color: accentHex } : undefined}
              >
                <MoreHorizontal className="h-5 w-5" />
                <span className="text-[10px] font-medium">More</span>
              </button>
            </div>

            <div
              id="mobile-secondary-navigation"
              className="flex w-1/2 shrink-0 justify-around px-2"
              aria-hidden={mobileNavPage !== 'secondary'}
            >
              <button
                type="button"
                onClick={() => setMobileNavPage('primary')}
                tabIndex={mobileNavPage === 'secondary' ? 0 : -1}
                className={`flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 px-1 ${
                  isSuperAdmin ? 'text-gray-500 hover:text-gold-400' : 'text-gray-500 hover:text-white'
                }`}
                aria-label="Back to primary navigation"
              >
                <ChevronLeft className="h-5 w-5" />
                <span className="text-[10px] font-medium">Back</span>
              </button>
              {mobileOverflowLinks.map(link => {
                const Icon = link.icon
                const isLinkActive = isActive(link.to, link.exact)
                return (
                  <Link
                    key={link.to}
                    to={link.to}
                    aria-current={isLinkActive ? 'page' : undefined}
                    tabIndex={mobileNavPage === 'secondary' ? 0 : -1}
                    className={`flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 px-1 ${
                      isLinkActive
                        ? isSuperAdmin ? 'text-gold-400' : ''
                        : isSuperAdmin ? 'text-gray-500 hover:text-gold-400' : 'text-gray-500 hover:text-white'
                    }`}
                    style={!isSuperAdmin && presentationVariant === 'legacy' && isLinkActive ? { color: accentHex } : undefined}
                  >
                    <div className="relative">
                      <Icon className="h-5 w-5" />
                      {link.to === '/dashboard/messages' && unreadCount > 0 && (
                        <span className="absolute -right-2 -top-2 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-none text-white">
                          {unreadBadge}
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] font-medium">{link.mobileLabel}</span>
                  </Link>
                )
              })}
              <Link
                to="/dashboard/settings"
                aria-current={location.pathname === '/dashboard/settings' ? 'page' : undefined}
                tabIndex={mobileNavPage === 'secondary' ? 0 : -1}
                className={`flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 px-1 ${
                  location.pathname === '/dashboard/settings'
                    ? isSuperAdmin ? 'text-gold-400' : ''
                    : isSuperAdmin ? 'text-gray-500 hover:text-gold-400' : 'text-gray-500 hover:text-white'
                }`}
                style={!isSuperAdmin && presentationVariant === 'legacy' && location.pathname === '/dashboard/settings' ? { color: accentHex } : undefined}
              >
                <User className="h-5 w-5" />
                <span className="text-[10px] font-medium">Profile</span>
              </Link>
            </div>
          </div>
        </div>
      </div>

    </div>
  )
}
