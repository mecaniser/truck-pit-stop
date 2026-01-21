import { NavLink, Routes, Route, Navigate } from 'react-router-dom'
import ServicesManagementPage from '@/features/dashboard/ServicesManagementPage'
import InventoryPage from '@/features/inventory/InventoryPage'
import MechanicsPage from '@/features/mechanics/MechanicsPage'
import SuppliersPage from '@/features/suppliers/SuppliersPage'

const tabClass =
  'px-4 py-2 text-sm font-medium rounded-lg transition-colors border border-transparent'

export default function MyGaragePage() {
  return (
    <div className="space-y-4">
      <div className="bg-white/5 border border-white/10 rounded-xl">
        <div className="flex flex-wrap gap-2 px-4 py-3 border-b border-white/10">
          <NavLink
            to="mechanics"
            className={({ isActive }) =>
              isActive
                ? `${tabClass} bg-amber-500/20 text-amber-200 border-amber-400/40`
                : `${tabClass} text-gray-200 hover:text-white hover:border-white/20`
            }
          >
            Mechanics
          </NavLink>
          <NavLink
            to="services"
            className={({ isActive }) =>
              isActive
                ? `${tabClass} bg-amber-500/20 text-amber-200 border-amber-400/40`
                : `${tabClass} text-gray-200 hover:text-white hover:border-white/20`
            }
          >
            Services
          </NavLink>
          <NavLink
            to="inventory"
            className={({ isActive }) =>
              isActive
                ? `${tabClass} bg-amber-500/20 text-amber-200 border-amber-400/40`
                : `${tabClass} text-gray-200 hover:text-white hover:border-white/20`
            }
          >
            Inventory
          </NavLink>
          <NavLink
            to="suppliers"
            className={({ isActive }) =>
              isActive
                ? `${tabClass} bg-amber-500/20 text-amber-200 border-amber-400/40`
                : `${tabClass} text-gray-200 hover:text-white hover:border-white/20`
            }
          >
            Suppliers
          </NavLink>
        </div>
        <div className="p-4">
          <Routes>
            <Route path="/" element={<Navigate to="mechanics" replace />} />
            <Route path="services" element={<ServicesManagementPage />} />
            <Route path="inventory" element={<InventoryPage />} />
            <Route path="mechanics" element={<MechanicsPage />} />
            <Route path="suppliers" element={<SuppliersPage />} />
          </Routes>
        </div>
      </div>
    </div>
  )
}
