import { useState } from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import CustomersPage from '../../features/customers/CustomersPage'
import VehiclesPage from '../../features/vehicles/VehiclesPage'
import RepairOrdersPage from '../../features/repair-orders/RepairOrdersPage'
import InventoryPage from '../../features/inventory/InventoryPage'
import DashboardHome from '../../features/dashboard/DashboardHome'
import AdminProfilePage from '../../features/dashboard/AdminProfilePage'
import ServicesManagementPage from '../../features/dashboard/ServicesManagementPage'

export default function DashboardLayout() {
  const { user } = useAuthStore()
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const navLinks = [
    { to: '/dashboard', label: 'Dashboard', exact: true },
    { to: '/dashboard/customers', label: 'Customers' },
    { to: '/dashboard/vehicles', label: 'Vehicles' },
    { to: '/dashboard/repair-orders', label: 'Repair Orders' },
    { to: '/dashboard/services', label: 'Services' },
    { to: '/dashboard/inventory', label: 'Inventory' },
  ]

  const isActive = (path: string, exact?: boolean) => 
    exact ? location.pathname === path : location.pathname === path

  const isOnSubPage = location.pathname !== '/dashboard'
  
  const getCurrentPageLabel = () => {
    if (location.pathname === '/dashboard/settings') return 'Profile Settings'
    const current = navLinks.find(link => location.pathname === link.to)
    return current?.label || ''
  }

  return (
    <div className="min-h-screen">
      <nav className="bg-white/90 backdrop-blur shadow-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex justify-between h-14 sm:h-16">
            {/* Logo */}
            <div className="flex items-center">
              <Link to="/dashboard" className="relative text-lg sm:text-xl font-bold text-slate-800 py-1">
                <svg className="absolute inset-0 w-full h-full opacity-15" viewBox="0 0 100 32" preserveAspectRatio="none" fill="none">
                  <style>{`
                    @keyframes checker { 0%, 100% { fill: #1e293b } 50% { fill: #f59e0b } }
                    @keyframes checkerAlt { 0%, 100% { fill: #f59e0b } 50% { fill: #1e293b } }
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
            </div>

            {/* Desktop nav */}
            <div className="hidden md:flex md:items-center md:space-x-6">
              {navLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`text-sm font-medium transition-colors ${
                    isActive(link.to, link.exact)
                      ? 'text-amber-600 border-b-2 border-amber-500'
                      : 'text-gray-600 hover:text-amber-600'
                  }`}
                >
                  {link.label}
                </Link>
              ))}
              <Link
                to="/dashboard/settings"
                className={`relative p-2.5 rounded-full transition-colors ${
                  location.pathname === '/dashboard/settings'
                    ? 'bg-amber-100 text-amber-600'
                    : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
                }`}
                title={`${user?.first_name} ${user?.last_name}`}
              >
                <svg className="absolute inset-0 w-full h-full" viewBox="0 0 40 40">
                  <style>{`
                    @keyframes ps1 { 0%, 100% { stroke: #1e293b } 50% { stroke: #f59e0b } }
                    @keyframes ps2 { 0%, 100% { stroke: #f59e0b } 50% { stroke: #1e293b } }
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

            {/* Mobile menu button */}
            <div className="flex items-center md:hidden">
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100 focus:outline-none"
                aria-label="Toggle menu"
              >
                {mobileMenuOpen ? (
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                ) : (
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile menu */}
        {mobileMenuOpen && (
          <div className="md:hidden bg-white/95 backdrop-blur border-t border-gray-200">
            <div className="px-4 py-3 space-y-2">
              {navLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`block px-3 py-2 rounded-lg text-base font-medium transition-colors ${
                    isActive(link.to, link.exact)
                      ? 'bg-amber-100 text-amber-700'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  {link.label}
                </Link>
              ))}
              <div className="border-t border-gray-200 pt-3 mt-3">
                <Link
                  to="/dashboard/settings"
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-base font-medium transition-colors ${
                    location.pathname === '/dashboard/settings'
                      ? 'bg-amber-100 text-amber-700'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Profile Settings
                </Link>
              </div>
            </div>
          </div>
        )}
      </nav>

      <main className="px-4 py-4 sm:py-6 max-w-7xl mx-auto">
        {/* Breadcrumb - only show on sub-pages */}
        {isOnSubPage && (
          <div className="mb-4 flex items-center gap-2 text-sm">
            <Link 
              to="/dashboard" 
              className="text-gray-400 hover:text-amber-500 transition-colors flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Dashboard
            </Link>
            <span className="text-gray-600">/</span>
            <span className="text-white font-medium">{getCurrentPageLabel()}</span>
          </div>
        )}
        <Routes>
          <Route path="customers" element={<CustomersPage />} />
          <Route path="vehicles" element={<VehiclesPage />} />
          <Route path="repair-orders" element={<RepairOrdersPage />} />
          <Route path="services" element={<ServicesManagementPage />} />
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="settings" element={<AdminProfilePage />} />
          <Route path="" element={<DashboardHome />} />
        </Routes>
      </main>
    </div>
  )
}
