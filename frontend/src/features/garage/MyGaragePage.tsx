import { NavLink, Routes, Route, Navigate } from 'react-router-dom'
import { BarChart3, Boxes, ClipboardList, Clock3, ShoppingCart, Wrench, type LucideIcon } from 'lucide-react'
import ServicesManagementPage from '@/features/dashboard/ServicesManagementPage'
import InventoryPage from '@/features/inventory/InventoryPage'
import PurchasingWorkspace from '@/features/inventory/PurchasingWorkspace'
import CounterSalesWorkspace from '@/features/inventory/CounterSalesWorkspace'
import MechanicsPage from '@/features/mechanics/MechanicsPage'
import GarageAnalyticsPage from './GarageAnalyticsPage'
import LaborBookTimePage from './LaborBookTimePage'
import GoogleReviewsPage from '@/features/reviews/GoogleReviewsPage'
import GoogleReviewsSettingsPage from '@/features/reviews/GoogleReviewsSettingsPage'

type GarageSection = {
  to: string
  label: string
  shortLabel: string
  icon: LucideIcon
}

const OPERATIONAL_SECTIONS: GarageSection[] = [
  { to: 'inventory', label: 'Inventory', shortLabel: 'Inventory', icon: Boxes },
  { to: 'purchasing', label: 'Purchasing', shortLabel: 'Purchasing', icon: ShoppingCart },
  { to: 'services', label: 'Services', shortLabel: 'Services', icon: ClipboardList },
  { to: 'labor-book-time', label: 'Labor Book Time', shortLabel: 'Book Time', icon: Clock3 },
]

const SECONDARY_SECTIONS: GarageSection[] = [
  { to: 'mechanics', label: 'Team', shortLabel: 'Team', icon: Wrench },
  { to: 'analytics', label: 'Analytics', shortLabel: 'Analytics', icon: BarChart3 },
]

function GarageLinks({ sections }: { sections: GarageSection[] }) {
  return sections.map(section => (
    <NavLink
      key={section.to}
      to={section.to}
      aria-label={section.label}
      className={({ isActive }) =>
        `db-my-shop-nav-item flex min-h-11 items-center gap-2 rounded-xl border px-3 py-2.5 text-xs font-medium transition-[color,background-color,border-color] duration-150 sm:text-sm ${
          isActive
            ? 'border-[var(--accent-500)]/30 bg-[var(--accent-500)]/10 text-[var(--accent-400)]'
            : 'border-transparent text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-300'
        }`
      }
    >
      <section.icon aria-hidden="true" className="h-4 w-4 shrink-0" />
      <span aria-hidden="true" className="db-my-shop-nav-label db-my-shop-nav-label-short whitespace-nowrap">
        {section.shortLabel}
      </span>
      <span aria-hidden="true" className="db-my-shop-nav-label db-my-shop-nav-label-full whitespace-nowrap">
        {section.label}
      </span>
    </NavLink>
  ))
}

function GarageNav() {
  return (
    <nav
      aria-label="Shop sections"
      data-shop-menu-layout="container-adaptive"
      className="db-my-shop-navigation shrink-0 p-2"
    >
      <div className="db-my-shop-nav-groups scrollbar-dark">
        <div
          role="group"
          aria-label="Shop operations"
          data-shop-menu-cluster="operational"
          className="db-my-shop-nav-cluster db-my-shop-nav-cluster-operational"
        >
          <GarageLinks sections={OPERATIONAL_SECTIONS} />
        </div>
        <div
          role="group"
          aria-label="Shop administration and insights"
          data-shop-menu-cluster="secondary"
          className="db-my-shop-nav-cluster db-my-shop-nav-cluster-secondary"
        >
          <GarageLinks sections={SECONDARY_SECTIONS} />
        </div>
      </div>
    </nav>
  )
}

export default function MyGaragePage() {
  return (
    <div className="db-my-shop-workspace db-operating-surface w-full">
      <div className="db-my-shop-layout">
        <GarageNav />

        {/* Every routed section is an operating surface and owns its own
            scroller, so this frame clips rather than offering a second one. */}
        <div className="db-my-shop-content db-operating-surface__frame min-w-0 scrollbar-dark">
          <Routes>
            <Route index element={<Navigate to="inventory" replace />} />
            <Route path="services" element={<ServicesManagementPage />} />
            <Route path="labor-book-time" element={<LaborBookTimePage />} />
            <Route path="inventory" element={<InventoryPage />} />
            <Route path="inventory/sales" element={<CounterSalesWorkspace />} />
            <Route path="purchasing" element={<PurchasingWorkspace />} />
            <Route path="mechanics" element={<MechanicsPage />} />
            <Route path="suppliers" element={<Navigate to="/dashboard/garage/purchasing?view=suppliers" replace />} />
            <Route path="reviews" element={<GoogleReviewsPage />} />
            <Route path="reviews/settings" element={<GoogleReviewsSettingsPage />} />
            <Route path="analytics" element={<GarageAnalyticsPage />} />
          </Routes>
        </div>
      </div>
    </div>
  )
}
