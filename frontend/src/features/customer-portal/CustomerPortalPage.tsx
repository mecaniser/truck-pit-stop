import { useState } from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { Customer, Vehicle, RepairOrder } from '../../types'
import { format } from 'date-fns'
import ServicesPage from '../services/ServicesPage'
import BookingPage from '../booking/BookingPage'
import AppointmentsPage from '../appointments/AppointmentsPage'
import ProfileSettingsPage from './ProfileSettingsPage'

const STATUS_BADGE_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  quoted: 'bg-blue-100 text-blue-700',
  approved: 'bg-cyan-100 text-cyan-700',
  in_progress: 'bg-amber-100 text-amber-700',
  completed: 'bg-green-100 text-green-700',
  invoiced: 'bg-purple-100 text-purple-700',
  paid: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-red-100 text-red-700',
}

function CustomerDashboard() {
  const { user } = useAuthStore()
  const { data: customer } = useQuery<Customer>({
    queryKey: ['customer', user?.customer_id],
    queryFn: async () => {
      if (!user?.customer_id) return null
      const response = await api.get(`/customers/${user.customer_id}`)
      return response.data
    },
    enabled: !!user?.customer_id,
  })

  const { data: vehicles } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles')
      return response.data
    },
  })

  const { data: repairOrders } = useQuery<RepairOrder[]>({
    queryKey: ['repair-orders'],
    queryFn: async () => {
      const response = await api.get('/repair-orders')
      return response.data
    },
  })

  const activeRepairs = repairOrders?.filter(o => 
    ['in_progress', 'approved', 'quoted'].includes(o.status)
  ).length || 0

  const completedRepairs = repairOrders?.filter(o => 
    ['completed', 'invoiced', 'paid'].includes(o.status)
  ).length || 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">
          Welcome back, {customer?.first_name || user?.email}
        </h1>
        <p className="text-gray-400 mt-1">Manage your vehicles and track repair status</p>
      </div>

      {/* KPI Cards - Compact on mobile, expanded on desktop */}
      {/* Mobile: Single compact card */}
      <div className="sm:hidden bg-white/5 rounded-xl p-4 border border-white/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-cyan-500/20 flex items-center justify-center text-2xl">
              🚛
            </div>
            <div>
              <div className="text-2xl font-bold text-white">{vehicles?.length || 0}</div>
              <div className="text-xs text-gray-400">Vehicles</div>
            </div>
          </div>
          <div className="flex gap-4">
            <div className="text-center">
              <div className="text-lg font-bold text-amber-400">{activeRepairs}</div>
              <div className="text-[10px] text-gray-500">Active</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-green-400">{completedRepairs}</div>
              <div className="text-[10px] text-gray-500">Done</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-purple-400">{repairOrders?.length || 0}</div>
              <div className="text-[10px] text-gray-500">Total</div>
            </div>
          </div>
        </div>
      </div>

      {/* Desktop: Full KPI cards */}
      <div className="hidden sm:grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-cyan-500/20 to-cyan-600/10 border-cyan-500/30 rounded-xl p-5 border">
          <div className="text-2xl">🚛</div>
          <div className="mt-3">
            <div className="text-4xl font-bold text-white">{vehicles?.length || 0}</div>
            <div className="text-sm text-gray-400 mt-1">My Vehicles</div>
          </div>
        </div>
        <div className="bg-gradient-to-br from-amber-500/20 to-amber-600/10 border-amber-500/30 rounded-xl p-5 border">
          <div className="text-2xl">🔧</div>
          <div className="mt-3">
            <div className="text-4xl font-bold text-white">{activeRepairs}</div>
            <div className="text-sm text-gray-400 mt-1">Active Repairs</div>
          </div>
        </div>
        <div className="bg-gradient-to-br from-green-500/20 to-green-600/10 border-green-500/30 rounded-xl p-5 border">
          <div className="text-2xl">✅</div>
          <div className="mt-3">
            <div className="text-4xl font-bold text-white">{completedRepairs}</div>
            <div className="text-sm text-gray-400 mt-1">Completed</div>
          </div>
        </div>
        <div className="bg-gradient-to-br from-purple-500/20 to-purple-600/10 border-purple-500/30 rounded-xl p-5 border">
          <div className="text-2xl">📋</div>
          <div className="mt-3">
            <div className="text-4xl font-bold text-white">{repairOrders?.length || 0}</div>
            <div className="text-sm text-gray-400 mt-1">Total Orders</div>
          </div>
        </div>
      </div>

      {/* Two Column Layout */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* My Vehicles */}
        <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">My Vehicles</h2>
            <Link to="/portal/vehicles" className="text-sm text-amber-500 hover:text-amber-400">
              View All
            </Link>
          </div>
          {vehicles && vehicles.length > 0 ? (
            <div className="space-y-2 sm:space-y-3">
              {vehicles.slice(0, 4).map((vehicle) => (
                <div
                  key={vehicle.id}
                  className="bg-white/5 rounded-lg p-2.5 sm:p-3 border border-white/5 hover:bg-white/10 active:bg-white/15 transition-colors"
                >
                  <div className="flex items-center gap-2 sm:gap-3">
                    <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-cyan-500/20 flex items-center justify-center text-base sm:text-lg shrink-0">
                      🚛
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-white text-sm sm:text-base truncate">
                        {vehicle.year} {vehicle.make} {vehicle.model}
                      </p>
                      <p className="text-xs sm:text-sm text-gray-400 truncate">
                        {vehicle.license_plate ? `Plate: ${vehicle.license_plate}` : 'No plate'}
                        {vehicle.mileage && ` • ${vehicle.mileage.toLocaleString()} mi`}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <div className="text-3xl mb-2">🚛</div>
              <p className="text-gray-400">No vehicles registered</p>
            </div>
          )}
        </div>

        {/* Recent Repairs */}
        <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Recent Repairs</h2>
            <Link to="/portal/repairs" className="text-sm text-amber-500 hover:text-amber-400">
              View All
            </Link>
          </div>
          {repairOrders && repairOrders.length > 0 ? (
            <div className="space-y-2 sm:space-y-3">
              {repairOrders.slice(0, 5).map((order) => (
                <div
                  key={order.id}
                  className="bg-white/5 rounded-lg p-2.5 sm:p-3 border border-white/5 hover:bg-white/10 active:bg-white/15 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                        <span className="font-medium text-white text-xs sm:text-sm">{order.order_number}</span>
                        <span className={`px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}>
                          {order.status.replace('_', ' ')}
                        </span>
                      </div>
                      {order.description && (
                        <p className="text-gray-400 text-xs sm:text-sm truncate mt-1">{order.description}</p>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-xs sm:text-sm font-medium text-white">
                        ${parseFloat(order.total_cost).toFixed(2)}
                      </div>
                      <div className="text-[10px] sm:text-xs text-gray-500">
                        {format(new Date(order.created_at), 'MMM d')}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <div className="text-3xl mb-2">📋</div>
              <p className="text-gray-400">No repair history</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function CustomerVehicles() {
  const { data: vehicles, isLoading } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles')
      return response.data
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">My Vehicles</h1>
        <p className="text-gray-400 mt-1">All vehicles registered to your account</p>
      </div>

      <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
        {vehicles && vehicles.length > 0 ? (
          <div className="divide-y divide-white/5">
            {vehicles.map((vehicle) => (
              <div key={vehicle.id} className="p-3 sm:p-6 hover:bg-white/5 active:bg-white/10 transition-colors">
                <div className="flex items-start gap-3 sm:gap-4">
                  <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-cyan-500/20 flex items-center justify-center text-xl sm:text-2xl shrink-0">
                    🚛
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-white text-base sm:text-lg">
                      {vehicle.year} {vehicle.make} {vehicle.model}
                    </h3>
                    <div className="flex flex-wrap gap-x-4 sm:gap-x-6 gap-y-1 mt-1.5 sm:mt-2 text-xs sm:text-sm text-gray-400">
                      {vehicle.vin && <span className="truncate max-w-[150px] sm:max-w-none">VIN: {vehicle.vin}</span>}
                      {vehicle.license_plate && <span>Plate: {vehicle.license_plate}</span>}
                      {vehicle.mileage && <span>{vehicle.mileage.toLocaleString()} mi</span>}
                      {vehicle.color && <span>{vehicle.color}</span>}
                    </div>
                    {vehicle.notes && (
                      <p className="text-gray-500 text-xs sm:text-sm mt-2 line-clamp-2">{vehicle.notes}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="text-4xl mb-3">🚛</div>
            <p className="text-gray-400">No vehicles registered yet</p>
          </div>
        )}
      </div>
    </div>
  )
}

function CustomerRepairs() {
  const { data: orders, isLoading } = useQuery<RepairOrder[]>({
    queryKey: ['repair-orders'],
    queryFn: async () => {
      const response = await api.get('/repair-orders')
      return response.data
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Repair History</h1>
        <p className="text-gray-400 mt-1">Track all your past and current repairs</p>
      </div>

      <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
        {orders && orders.length > 0 ? (
          <div className="divide-y divide-white/5">
            {orders.map((order) => (
              <div key={order.id} className="p-3 sm:p-6 hover:bg-white/5 active:bg-white/10 transition-colors">
                <div className="flex items-start justify-between gap-3 sm:gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
                      <h3 className="font-semibold text-white text-sm sm:text-base">{order.order_number}</h3>
                      <span className={`px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-full text-[10px] sm:text-xs font-medium ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}>
                        {order.status.replace('_', ' ')}
                      </span>
                    </div>
                    {order.description && (
                      <p className="text-gray-400 text-sm mt-1.5 sm:mt-2 line-clamp-2">{order.description}</p>
                    )}
                    <p className="text-xs sm:text-sm text-gray-500 mt-1.5 sm:mt-2">
                      {format(new Date(order.created_at), 'MMM d, yyyy')}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-lg sm:text-xl font-bold text-white">
                      ${parseFloat(order.total_cost).toFixed(2)}
                    </div>
                    <div className="text-[10px] sm:text-xs text-gray-500 mt-0.5 sm:mt-1">Total</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="text-4xl mb-3">📋</div>
            <p className="text-gray-400">No repair history yet</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function CustomerPortalPage() {
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const navLinks = [
    { to: '/portal', label: 'Dashboard', exact: true },
    { to: '/portal/services', label: 'Services' },
    { to: '/portal/appointments', label: 'Appointments' },
    { to: '/portal/vehicles', label: 'Vehicles' },
    { to: '/portal/repairs', label: 'History' },
  ]

  const isActive = (path: string, exact?: boolean) => 
    exact ? location.pathname === path : location.pathname === path

  const isOnSubPage = location.pathname !== '/portal'
  
  const getCurrentPageLabel = () => {
    if (location.pathname.startsWith('/portal/book/')) return 'Book Appointment'
    if (location.pathname === '/portal/settings') return 'Profile Settings'
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
              <Link to="/portal" className="relative text-lg sm:text-xl font-bold text-slate-800 py-1">
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
                to="/portal/settings"
                className={`relative p-2.5 rounded-full transition-colors ${
                  location.pathname === '/portal/settings'
                    ? 'bg-amber-100 text-amber-600'
                    : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
                }`}
                title="Profile Settings"
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
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
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
                  to="/portal/settings"
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-base font-medium transition-colors ${
                    location.pathname === '/portal/settings'
                      ? 'bg-amber-100 text-amber-700'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
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
              to="/portal" 
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
          <Route path="" element={<CustomerDashboard />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="book/:serviceId" element={<BookingPage />} />
          <Route path="appointments" element={<AppointmentsPage />} />
          <Route path="vehicles" element={<CustomerVehicles />} />
          <Route path="repairs" element={<CustomerRepairs />} />
          <Route path="settings" element={<ProfileSettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}


