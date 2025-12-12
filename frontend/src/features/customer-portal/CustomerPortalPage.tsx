import { useState } from 'react'
import { Routes, Route, Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { Customer, Vehicle, RepairOrder } from '../../types'
import { format } from 'date-fns'

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Welcome, {customer?.first_name || user?.email}</h1>
        <p className="text-gray-200">Manage your vehicles and view repair history</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
        <div className="bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-6 rounded-xl shadow-lg">
          <h2 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 text-slate-800">My Vehicles</h2>
          {vehicles && vehicles.length > 0 ? (
            <ul className="space-y-2">
              {vehicles.map((vehicle) => (
                <li key={vehicle.id} className="border-b pb-2">
                  <p className="font-medium">{vehicle.year} {vehicle.make} {vehicle.model}</p>
                  {vehicle.license_plate && (
                    <p className="text-sm text-gray-600">Plate: {vehicle.license_plate}</p>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-500">No vehicles registered</p>
          )}
          <Link
            to="/portal/vehicles"
            className="mt-4 inline-block text-indigo-600 hover:text-indigo-800"
          >
            Manage Vehicles →
          </Link>
        </div>

        <div className="bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-6 rounded-xl shadow-lg">
          <h2 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 text-slate-800">Recent Repairs</h2>
          {repairOrders && repairOrders.length > 0 ? (
            <ul className="space-y-2">
              {repairOrders.slice(0, 5).map((order) => (
                <li key={order.id} className="border-b pb-2">
                  <p className="font-medium">{order.order_number}</p>
                  <p className="text-sm text-gray-600">
                    {format(new Date(order.created_at), 'MMM d, yyyy')} - ${parseFloat(order.total_cost).toFixed(2)}
                  </p>
                  <span className={`inline-block mt-1 px-2 py-1 rounded text-xs ${order.status === 'paid' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
                    {order.status.replace('_', ' ')}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-500">No repair history</p>
          )}
          <Link
            to="/portal/repairs"
            className="mt-4 inline-block text-indigo-600 hover:text-indigo-800"
          >
            View All Repairs →
          </Link>
        </div>
      </div>
    </div>
  )
}

function CustomerVehicles() {
  const { user } = useAuthStore()
  const { data: vehicles, isLoading } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles')
      return response.data
    },
  })

  if (isLoading) {
    return <div>Loading...</div>
  }

  return (
    <div>
      <h1 className="text-xl sm:text-2xl font-bold mb-3 sm:mb-4 text-slate-800">My Vehicles</h1>
      <div className="bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 shadow-lg overflow-hidden rounded-xl">
        <ul className="divide-y divide-gray-200">
          {vehicles?.map((vehicle) => (
            <li key={vehicle.id}>
              <div className="px-4 py-4 sm:px-6">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-indigo-600 truncate">
                    {vehicle.year} {vehicle.make} {vehicle.model}
                  </p>
                </div>
                <div className="mt-2 sm:flex sm:justify-between">
                  <div className="sm:flex">
                    {vehicle.vin && (
                      <p className="flex items-center text-sm text-gray-500">
                        VIN: {vehicle.vin}
                      </p>
                    )}
                    {vehicle.license_plate && (
                      <p className="mt-2 flex items-center text-sm text-gray-500 sm:mt-0 sm:ml-6">
                        Plate: {vehicle.license_plate}
                      </p>
                    )}
                    {vehicle.mileage && (
                      <p className="mt-2 flex items-center text-sm text-gray-500 sm:mt-0 sm:ml-6">
                        Mileage: {vehicle.mileage.toLocaleString()} mi
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
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
    return <div>Loading...</div>
  }

  return (
    <div>
      <h1 className="text-xl sm:text-2xl font-bold mb-3 sm:mb-4 text-slate-800">Repair History</h1>
      <div className="bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 shadow-lg overflow-hidden rounded-xl">
        <ul className="divide-y divide-gray-200">
          {orders?.map((order) => (
            <li key={order.id}>
              <div className="px-4 py-4 sm:px-6">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-indigo-600 truncate">
                    {order.order_number}
                  </p>
                  <span className="text-sm font-medium text-gray-900">
                    ${parseFloat(order.total_cost).toFixed(2)}
                  </span>
                </div>
                <div className="mt-2">
                  <p className="text-sm text-gray-500">
                    {format(new Date(order.created_at), 'MMMM d, yyyy')}
                  </p>
                  {order.description && (
                    <p className="mt-1 text-sm text-gray-700">{order.description}</p>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default function CustomerPortalPage() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const navLinks = [
    { to: '/portal', label: 'Dashboard', exact: true },
    { to: '/portal/vehicles', label: 'My Vehicles' },
    { to: '/portal/repairs', label: 'Repair History' },
  ]

  const isActive = (path: string, exact?: boolean) => 
    exact ? location.pathname === path : location.pathname.startsWith(path)

  return (
    <div className="min-h-screen">
      <nav className="bg-white/90 backdrop-blur shadow-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex justify-between h-14 sm:h-16">
            {/* Logo */}
            <div className="flex items-center">
              <Link to="/portal" className="text-lg sm:text-xl font-bold text-slate-800">
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
        <Routes>
          <Route path="" element={<CustomerDashboard />} />
          <Route path="vehicles" element={<CustomerVehicles />} />
          <Route path="repairs" element={<CustomerRepairs />} />
        </Routes>
      </main>
    </div>
  )
}


