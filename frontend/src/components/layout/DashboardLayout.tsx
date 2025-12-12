import { useState } from 'react'
import { Routes, Route, Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import CustomersPage from '../../features/customers/CustomersPage'
import VehiclesPage from '../../features/vehicles/VehiclesPage'
import RepairOrdersPage from '../../features/repair-orders/RepairOrdersPage'

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
    { to: '/dashboard/customers', label: 'Customers' },
    { to: '/dashboard/vehicles', label: 'Vehicles' },
    { to: '/dashboard/repair-orders', label: 'Repair Orders' },
  ]

  const isActive = (path: string) => location.pathname === path

  return (
    <div className="min-h-screen">
      <nav className="bg-white/90 backdrop-blur shadow-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex justify-between h-14 sm:h-16">
            {/* Logo */}
            <div className="flex items-center">
              <Link to="/dashboard" className="text-lg sm:text-xl font-bold text-slate-800">
                Truck Pit Stop
              </Link>
            </div>

            {/* Desktop nav */}
            <div className="hidden md:flex md:items-center md:space-x-6">
              {navLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`text-sm font-medium transition-colors ${
                    isActive(link.to)
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
                    isActive(link.to)
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
        <Routes>
          <Route path="customers" element={<CustomersPage />} />
          <Route path="vehicles" element={<VehiclesPage />} />
          <Route path="repair-orders" element={<RepairOrdersPage />} />
          <Route path="" element={
            <div className="text-center py-12">
              <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">Welcome to Dashboard</h1>
              <p className="text-gray-300">Select a section from the menu to get started</p>
            </div>
          } />
        </Routes>
      </main>
    </div>
  )
}
