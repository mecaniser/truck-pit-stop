import { Routes, Route, Link, useNavigate } from 'react-router-dom'
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
        <h1 className="text-2xl font-bold">Welcome, {customer?.first_name || user?.email}</h1>
        <p className="text-gray-600">Manage your vehicles and view repair history</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">My Vehicles</h2>
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

        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">Recent Repairs</h2>
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
      <h1 className="text-2xl font-bold mb-4">My Vehicles</h1>
      <div className="bg-white shadow overflow-hidden sm:rounded-md">
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
      <h1 className="text-2xl font-bold mb-4">Repair History</h1>
      <div className="bg-white shadow overflow-hidden sm:rounded-md">
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

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex">
              <div className="flex-shrink-0 flex items-center">
                <h1 className="text-xl font-bold text-gray-900">Truck Pit Stop</h1>
              </div>
              <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
                <Link
                  to="/portal"
                  className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                >
                  Dashboard
                </Link>
                <Link
                  to="/portal/vehicles"
                  className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                >
                  My Vehicles
                </Link>
                <Link
                  to="/portal/repairs"
                  className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                >
                  Repair History
                </Link>
              </div>
            </div>
            <div className="flex items-center">
              <span className="text-sm text-gray-700 mr-4">{user?.email}</span>
              <button
                onClick={handleLogout}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <Routes>
          <Route path="" element={<CustomerDashboard />} />
          <Route path="vehicles" element={<CustomerVehicles />} />
          <Route path="repairs" element={<CustomerRepairs />} />
        </Routes>
      </main>
    </div>
  )
}

