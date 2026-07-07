import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../../stores/authStore'
import { Home, Users, ClipboardList, Building2, User, LayoutGrid, BarChart3, UserCheck, Crown, MessageSquare, Truck } from 'lucide-react'
import { useTheme } from '../../contexts/ThemeContext'
import api from '@/lib/api'
import CustomersPage from '@/features/customers/CustomersPage'
import RepairOrdersPage from '@/features/repair-orders/RepairOrdersPage'
import MyGaragePage from '@/features/garage/MyGaragePage'
import DashboardHome from '@/features/dashboard/DashboardHome'
import UnifiedSettingsPage from '@/features/dashboard/UnifiedSettingsPage'
import PlatformDashboard from '@/features/platform-admin/PlatformDashboard'
import GaragesPage from '@/features/platform-admin/GaragesPage'
import GarageAnalyticsPage from '@/features/platform-admin/GarageAnalyticsPage'
import PlatformAnalyticsPage from '@/features/platform-admin/PlatformAnalyticsPage'
import PendingEnrollmentsPage from '@/features/platform-admin/PendingEnrollmentsPage'
import MessagesInboxPage from '@/features/messages/MessagesInboxPage'
import MechanicsBoardPage from '@/features/dashboard/MechanicsBoardPage'
import MechanicBoardDetailPage from '@/features/dashboard/MechanicBoardDetailPage'
import type { MessagesUnreadSummary } from '@/types'
import BrandLogo from '../brand/BrandLogo'
import TenantBrandLogo from '../brand/TenantBrandLogo'
import useTenantBranding from '@/hooks/useTenantBranding'

export default function DashboardLayout() {
  const { user } = useAuthStore()
  const location = useLocation()
  const { accentColors } = useTheme()
  // Owner/admin/receptionist/mechanic have messaging by role; other roles
  // (notably fleet managers) need the can_access_messaging grant.
  const canAccessMessaging =
    ['garage_owner', 'garage_admin', 'receptionist', 'mechanic'].includes(user?.role || '') ||
    Boolean(user?.can_access_messaging)
  const messagesNavLink = { to: '/dashboard/messages', label: 'Messages', mobileLabel: 'Messages', icon: MessageSquare }
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

  // Garage owner/admin own the fleet, so they get a Fleet link into the board.
  // Fleet managers never reach this dashboard (StaffRoute sends them to /fleet).
  const canAccessFleet = user?.role === 'garage_owner' || user?.role === 'garage_admin'

  // Different navigation for SUPER_ADMIN (platform management) vs garage staff
  const navLinks = user?.role === 'super_admin'
    ? [
        { to: '/dashboard', label: 'Dashboard', mobileLabel: 'Home', exact: true, icon: Home },
        { to: '/dashboard/garages', label: 'Shops', mobileLabel: 'Shops', icon: LayoutGrid },
        { to: '/dashboard/pending-enrollments', label: 'Enrollments', mobileLabel: 'Enroll', icon: UserCheck },
        { to: '/dashboard/analytics', label: 'Analytics', mobileLabel: 'Stats', icon: BarChart3 },
      ]
    : [
        { to: '/dashboard', label: 'Dashboard', mobileLabel: 'Home', exact: true, icon: Home },
        { to: '/dashboard/customers', label: 'Customers', mobileLabel: 'Customers', icon: Users },
        { to: '/dashboard/repair-orders', label: 'Repair Orders', mobileLabel: 'Orders', icon: ClipboardList },
        ...(canAccessFleet ? [{ to: '/fleet', label: 'Fleet', mobileLabel: 'Fleet', icon: Truck }] : []),
        ...(canAccessMessaging ? [messagesNavLink] : []),
        { to: '/dashboard/garage', label: 'My Shop', mobileLabel: 'Shop', icon: Building2 },
      ]

  const isActive = (path: string, exact?: boolean) => 
    exact ? location.pathname === path : location.pathname.startsWith(path)

  const isOnSubPage = location.pathname !== '/dashboard'
  
  const getCurrentPageLabel = () => {
    if (location.pathname === '/dashboard/settings') return 'Profile Settings'
    if (location.pathname === '/dashboard/mechanics') return 'Technician Board'
    if (location.pathname.startsWith('/dashboard/mechanics/')) return 'Technician Detail'
    const current = navLinks.find(link => location.pathname === link.to)
    return current?.label || ''
  }

  const isSuperAdmin = user?.role === 'super_admin'
  const isGarageWorkspaceRoute =
    !isSuperAdmin &&
    (location.pathname === '/dashboard/garage' || location.pathname.startsWith('/dashboard/garage/'))
  const dashboardLogoAlt = isSuperAdmin
    ? 'Diesel Bridge Network'
    : tenantBranding?.name || user?.tenant_name || 'Diesel Bridge Network'
  const dashboardAriaLabel = isSuperAdmin
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

  return (
    <div className={`h-screen overflow-hidden ${isGarageUser ? 'bg-blueNoir-900' : ''}`}>
      <nav className={`sticky top-0 z-50 ${
        isSuperAdmin 
          ? 'bg-noir-900/95 backdrop-blur-xl border-b border-gold-500/20 shadow-lg shadow-gold-500/5' 
          : 'bg-blueNoir-800/95 backdrop-blur-xl border-b border-white/10 shadow-lg'
      }`}>
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex justify-between h-14 sm:h-16">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <Link to="/dashboard" className="inline-flex items-center py-1" aria-label={dashboardAriaLabel}>
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
              {isSuperAdmin && (
                <span className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-gold-500/10 border border-gold-500/30 rounded-full text-gold-400 text-xs font-medium">
                  <Crown className="w-3 h-3" />
                  Platform Admin
                </span>
              )}
            </div>

            {/* Desktop nav */}
            <div className="hidden md:flex md:items-center md:space-x-6">
              {navLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`text-sm font-medium transition-colors ${
                    isActive(link.to, link.exact)
                      ? isSuperAdmin 
                        ? 'text-gold-400 border-b-2 border-gold-500'
                        : 'border-b-2'
                      : isSuperAdmin
                        ? 'text-gray-400 hover:text-gold-400'
                        : 'text-gray-400 hover:text-white'
                  }`}
                  style={!isSuperAdmin && isActive(link.to, link.exact) ? { color: accentHex, borderColor: accentHex } : undefined}
                >
                  <span className="inline-flex items-center gap-2">
                    {link.label}
                    {link.to === '/dashboard/messages' && unreadCount > 0 && (
                      <span className="inline-flex min-w-[1.25rem] h-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-[11px] font-semibold leading-none text-white">
                        {unreadBadge}
                      </span>
                    )}
                  </span>
                </Link>
              ))}
              <Link
                to="/dashboard/settings"
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
                style={{
                  color: !isSuperAdmin && location.pathname === '/dashboard/settings' ? accentHex : undefined,
                  borderColor: !isSuperAdmin && location.pathname === '/dashboard/settings' ? profileTileBorder : undefined,
                  boxShadow: `0 10px 24px ${profileTileGlow}`,
                }}
                title={profileDisplayName}
              >
                <div
                  className="absolute inset-[3px] rounded-[14px] border border-white/5"
                  style={{ background: profileTileInset }}
                />
                <div className="relative flex h-full w-full items-center justify-center rounded-[14px]">
                  <span className="text-[11px] font-semibold tracking-[0.18em]">
                    {profileMonogram}
                  </span>
                </div>
                <span
                  className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 shadow-[0_0_10px_rgba(52,211,153,0.6)]"
                  style={{ backgroundColor: '#34d399', borderColor: isSuperAdmin ? '#0a0b0d' : '#10151f' }}
                />
              </Link>
            </div>

          </div>
        </div>
      </nav>

      <main
        className="px-4 sm:px-6 lg:px-8 py-4 sm:py-6 flex flex-col h-[calc(100vh-3.5rem)] sm:h-[calc(100vh-4rem)] overflow-hidden"
      >
        {/* Breadcrumb - only show on sub-pages */}
        {isOnSubPage && (
          <div className="mb-4 flex-shrink-0 flex items-center gap-2 text-sm">
            <Link
              to="/dashboard"
              className="transition-colors flex items-center gap-1 text-gray-400 hover:text-white"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Dashboard
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
          className={`flex-1 min-h-0 flex flex-col scrollbar-dark ${
            isGarageWorkspaceRoute ? 'overflow-y-auto lg:overflow-hidden' : 'overflow-y-auto'
          }`}
        >
          <Routes>
            {/* Platform Admin Routes (SUPER_ADMIN only) */}
            {user?.role === 'super_admin' ? (
              <>
                <Route path="garages" element={<GaragesPage />} />
                <Route path="garages/:garageId/analytics" element={<GarageAnalyticsPage />} />
                <Route path="pending-enrollments" element={<PendingEnrollmentsPage />} />
                <Route path="analytics" element={<PlatformAnalyticsPage />} />
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
          {/* Spacer so content clears the fixed bottom nav on mobile */}
          <div className="h-16 md:hidden flex-shrink-0" />
        </div>
      </main>

      {/* Mobile Bottom Navigation */}
      <div className="fixed bottom-0 left-0 right-0 z-50 md:hidden">
        <div className={`px-2 py-2 flex justify-around ${
          isSuperAdmin 
            ? 'bg-noir-900/95 backdrop-blur-xl border-t border-gold-500/20' 
            : 'bg-blueNoir-800/95 backdrop-blur-xl border-t border-white/10'
        }`}>
          {navLinks.map((link) => {
            const Icon = link.icon
            const isLinkActive = isActive(link.to, link.exact)
            return (
              <Link
                key={link.to}
                to={link.to}
                className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
                  isLinkActive
                    ? isSuperAdmin ? 'text-gold-400' : ''
                    : isSuperAdmin ? 'text-gray-500 hover:text-gold-400' : 'text-gray-500 hover:text-white'
                }`}
                style={!isSuperAdmin && isLinkActive ? { color: accentHex } : undefined}
              >
                <div className="relative">
                  <Icon className="w-5 h-5" />
                  {link.to === '/dashboard/messages' && unreadCount > 0 && (
                    <span className="absolute -top-2 -right-2 inline-flex min-w-[1rem] h-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-none text-white">
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
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname === '/dashboard/settings'
                ? isSuperAdmin ? 'text-gold-400' : ''
                : isSuperAdmin ? 'text-gray-500 hover:text-gold-400' : 'text-gray-500 hover:text-white'
            }`}
            style={!isSuperAdmin && location.pathname === '/dashboard/settings' ? { color: accentHex } : undefined}
          >
            <User className="w-5 h-5" />
            <span className="text-[10px] font-medium">Profile</span>
          </Link>
        </div>
      </div>

    </div>
  )
}
