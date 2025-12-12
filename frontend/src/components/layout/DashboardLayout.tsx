import { useState } from 'react'
import { Routes, Route, Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import CustomersPage from '../../features/customers/CustomersPage'
import VehiclesPage from '../../features/vehicles/VehiclesPage'
import RepairOrdersPage from '../../features/repair-orders/RepairOrdersPage'
import InventoryPage from '../../features/inventory/InventoryPage'
import DashboardHome from '../../features/dashboard/DashboardHome'

export default function DashboardLayout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const navLinks = [
    { to: '/dashboard', label: 'Dashboard', exact: true },
    { to: '/dashboard/customers', label: 'Customers' },
    { to: '/dashboard/vehicles', label: 'Vehicles' },
    { to: '/dashboard/repair-orders', label: 'Repair Orders' },
    { to: '/dashboard/inventory', label: 'Inventory' },
  ]

  const isActive = (path: string, exact?: boolean) => 
    exact ? location.pathname === path : location.pathname === path

  const isOnSubPage = location.pathname !== '/dashboard'
  
  const getCurrentPageLabel = () => {
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
              <Link to="/dashboard" className="relative text-lg sm:text-xl font-bold text-slate-800">
                <svg className="absolute inset-0 w-full h-full opacity-15" viewBox="0 0 100 24" preserveAspectRatio="none" fill="none">
                  <rect x="50" y="0" width="12.5" height="4" fill="#1e293b"/>
                  <rect x="62.5" y="0" width="12.5" height="4" fill="#f59e0b"/>
                  <rect x="75" y="0" width="12.5" height="4" fill="#1e293b"/>
                  <rect x="87.5" y="0" width="12.5" height="4" fill="#f59e0b"/>
                  <rect x="0" y="20" width="12.5" height="4" fill="#f59e0b"/>
                  <rect x="12.5" y="20" width="12.5" height="4" fill="#1e293b"/>
                  <rect x="25" y="20" width="12.5" height="4" fill="#f59e0b"/>
                  <rect x="37.5" y="20" width="12.5" height="4" fill="#1e293b"/>
                </svg>
                <span className="relative">Truck Pit Stop</span>
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
              <span className="text-sm text-gray-500 truncate max-w-32">{user?.email}</span>
              <button
                onClick={handleLogout}
                className="text-sm text-gray-500 hover:text-red-600 transition-colors"
              >
                Logout
              </button>
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
                <p className="px-3 text-sm text-gray-500 truncate">{user?.email}</p>
                <button
                  onClick={handleLogout}
                  className="mt-2 w-full text-left px-3 py-2 rounded-lg text-base font-medium text-red-600 hover:bg-red-50 transition-colors"
                >
                  Logout
                </button>
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
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="" element={<DashboardHome />} />
        </Routes>
      </main>
    </div>
  )
}
