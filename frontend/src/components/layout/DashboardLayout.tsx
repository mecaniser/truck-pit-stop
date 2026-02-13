import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { Home, Users, ClipboardList, Building2, User, LayoutGrid, BarChart3, UserCheck, Crown, MessageSquare } from 'lucide-react'
import { useTheme } from '../../contexts/ThemeContext'
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

export default function DashboardLayout() {
  const { user } = useAuthStore()
  const location = useLocation()
  const { accentColors } = useTheme()
  
  // Get the hex color for the current accent
  const accentHex = accentColors[500]

  // Different navigation for SUPER_ADMIN (platform management) vs garage staff
  const navLinks = user?.role === 'super_admin' 
    ? [
        { to: '/dashboard', label: 'Dashboard', mobileLabel: 'Home', exact: true, icon: Home },
        { to: '/dashboard/garages', label: 'Garages', mobileLabel: 'Garages', icon: LayoutGrid },
        { to: '/dashboard/pending-enrollments', label: 'Enrollments', mobileLabel: 'Enroll', icon: UserCheck },
        { to: '/dashboard/analytics', label: 'Analytics', mobileLabel: 'Stats', icon: BarChart3 },
      ]
    : [
        { to: '/dashboard', label: 'Dashboard', mobileLabel: 'Home', exact: true, icon: Home },
        { to: '/dashboard/customers', label: 'Customers', mobileLabel: 'Customers', icon: Users },
        { to: '/dashboard/repair-orders', label: 'Repair Orders', mobileLabel: 'Orders', icon: ClipboardList },
        { to: '/dashboard/messages', label: 'Messages', mobileLabel: 'Messages', icon: MessageSquare },
        { to: '/dashboard/garage', label: 'My Garage', mobileLabel: 'Garage', icon: Building2 },
      ]

  const isActive = (path: string, exact?: boolean) => 
    exact ? location.pathname === path : location.pathname.startsWith(path)

  const isOnSubPage = location.pathname !== '/dashboard'
  
  const getCurrentPageLabel = () => {
    if (location.pathname === '/dashboard/settings') return 'Profile Settings'
    if (location.pathname === '/dashboard/mechanics') return 'Mechanic Board'
    if (location.pathname.startsWith('/dashboard/mechanics/')) return 'Mechanic Detail'
    const current = navLinks.find(link => location.pathname === link.to)
    return current?.label || ''
  }

  const isSuperAdmin = user?.role === 'super_admin'

  // Garage users get BlueNoir theme
  const isGarageUser = !isSuperAdmin

  return (
    <div className={`min-h-screen ${isGarageUser ? 'bg-blueNoir-900' : ''}`}>
      <nav className={`sticky top-0 z-50 ${
        isSuperAdmin 
          ? 'bg-noir-900/95 backdrop-blur-xl border-b border-gold-500/20 shadow-lg shadow-gold-500/5' 
          : 'bg-blueNoir-800/95 backdrop-blur-xl border-b border-white/10 shadow-lg'
      }`}>
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex justify-between h-14 sm:h-16">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <Link to="/dashboard" className="relative text-lg sm:text-xl font-bold py-1 text-white">
                <svg className="absolute inset-0 w-full h-full opacity-15" viewBox="0 0 100 32" preserveAspectRatio="none" fill="none">
                  <style>{`
                    @keyframes checker { 0%, 100% { fill: ${isSuperAdmin ? '#B8860B' : accentHex} } 50% { fill: ${isSuperAdmin ? '#D4A84B' : '#ffffff'} } }
                    @keyframes checkerAlt { 0%, 100% { fill: ${isSuperAdmin ? '#D4A84B' : '#ffffff'} } 50% { fill: ${isSuperAdmin ? '#B8860B' : accentHex} } }
                    .t1 { animation: checker 2.5s ease-in-out infinite }
                    .t2 { animation: checkerAlt 2.5s ease-in-out infinite }
                    .b1 { animation: checker 2.5s ease-in-out infinite; animation-delay: -0.8s }
                    .b2 { animation: checkerAlt 2.5s ease-in-out infinite; animation-delay: -0.8s }
                  `}</style>
                  <rect x="50" y="0" width="12.5" height="4" className="t1"/>
                  <rect x="62.5" y="0" width="12.5" height="4" className="t2"/>
                  <rect x="75" y="0" width="12.5" height="4" className="t1"/>
                  <rect x="87.5" y="0" width="12.5" height="4" className="t2"/>
                  <rect x="0" y="28" width="12.5" height="4" className="b2"/>
                  <rect x="12.5" y="28" width="12.5" height="4" className="b1"/>
                  <rect x="25" y="28" width="12.5" height="4" className="b2"/>
                  <rect x="37.5" y="28" width="12.5" height="4" className="b1"/>
                </svg>
                <span className="relative px-1">Truck Pit Stop</span>
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
                  {link.label}
                </Link>
              ))}
              <Link
                to="/dashboard/settings"
                className={`relative p-2.5 rounded-full transition-colors ${
                  location.pathname === '/dashboard/settings'
                    ? isSuperAdmin
                      ? 'bg-gold-500/20 text-gold-400'
                      : 'bg-white/10'
                    : isSuperAdmin
                      ? 'text-gray-400 hover:bg-gold-500/10 hover:text-gold-400'
                      : 'text-gray-400 hover:bg-white/10 hover:text-white'
                }`}
                style={!isSuperAdmin && location.pathname === '/dashboard/settings' ? { color: accentHex } : undefined}
                title={`${user?.first_name} ${user?.last_name}`}
              >
                <svg className="absolute inset-0 w-full h-full" viewBox="0 0 40 40">
                  <style>{`
                    @keyframes ps1 { 0%, 100% { stroke: ${isSuperAdmin ? '#B8860B' : accentHex} } 50% { stroke: ${isSuperAdmin ? '#D4A84B' : '#ffffff'} } }
                    @keyframes ps2 { 0%, 100% { stroke: ${isSuperAdmin ? '#D4A84B' : '#ffffff'} } 50% { stroke: ${isSuperAdmin ? '#B8860B' : accentHex} } }
                    .ps1 { animation: ps1 2.5s ease-in-out infinite }
                    .ps2 { animation: ps2 2.5s ease-in-out infinite }
                  `}</style>
                  {[...Array(8)].map((_, i) => {
                    const startAngle = i * 45 - 90
                    const endAngle = startAngle + 45
                    const r = 17
                    const x1 = 20 + r * Math.cos(startAngle * Math.PI / 180)
                    const y1 = 20 + r * Math.sin(startAngle * Math.PI / 180)
                    const x2 = 20 + r * Math.cos(endAngle * Math.PI / 180)
                    const y2 = 20 + r * Math.sin(endAngle * Math.PI / 180)
                    return (
                      <path
                        key={i}
                        d={`M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`}
                        fill="none"
                        strokeWidth="3"
                        strokeLinecap="round"
                        className={i % 2 === 0 ? 'ps1' : 'ps2'}
                      />
                    )
                  })}
                </svg>
                <svg className="w-5 h-5 relative" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </Link>
            </div>

          </div>
        </div>
      </nav>

      <main className="px-4 sm:px-6 lg:px-8 py-4 sm:py-6 flex flex-col" style={{ minHeight: 'calc(100vh - 4rem)' }}>
        {/* Breadcrumb - only show on sub-pages */}
        {isOnSubPage && (
          <div className="mb-4 flex items-center gap-2 text-sm">
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
              <Route path="messages" element={<MessagesInboxPage />} />
              <Route path="mechanics" element={<MechanicsBoardPage />} />
              <Route path="mechanics/:mechanicId" element={<MechanicBoardDetailPage />} />
              <Route path="garage/*" element={<MyGaragePage />} />
              <Route path="settings" element={<UnifiedSettingsPage />} />
              <Route path="" element={<DashboardHome />} />
            </>
          )}
        </Routes>
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
                <Icon className="w-5 h-5" />
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

      {/* Spacer for bottom nav on mobile */}
      <div className="h-16 md:hidden" />
    </div>
  )
}
