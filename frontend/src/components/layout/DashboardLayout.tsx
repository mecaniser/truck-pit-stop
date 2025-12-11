import { Routes, Route, Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import CustomersPage from '../../features/customers/CustomersPage'
import VehiclesPage from '../../features/vehicles/VehiclesPage'
import RepairOrdersPage from '../../features/repair-orders/RepairOrdersPage'

export default function DashboardLayout() {
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
                  to="/dashboard/customers"
                  className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                >
                  Customers
                </Link>
                <Link
                  to="/dashboard/vehicles"
                  className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                >
                  Vehicles
                </Link>
                <Link
                  to="/dashboard/repair-orders"
                  className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
                >
                  Repair Orders
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
          <Route path="customers" element={<CustomersPage />} />
          <Route path="vehicles" element={<VehiclesPage />} />
          <Route path="repair-orders" element={<RepairOrdersPage />} />
          <Route path="" element={<div>Dashboard Home</div>} />
        </Routes>
      </main>
    </div>
  )
}

