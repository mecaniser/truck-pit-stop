import { NavLink, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { BarChart3, Boxes, ChevronRight, ClipboardList, Clock3, Settings2, ShoppingCart, Wrench, type LucideIcon } from 'lucide-react'
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
  { to: 'services', label: 'Services', shortLabel: 'Services', icon: ClipboardList },
  { to: 'labor-book-time', label: 'Labor Book Time', shortLabel: 'Book Time', icon: Clock3 },
  { to: 'inventory', label: 'Inventory', shortLabel: 'Inventory', icon: Boxes },
  { to: 'purchasing', label: 'Purchasing', shortLabel: 'Purchasing', icon: ShoppingCart },
]

const SECONDARY_SECTIONS: GarageSection[] = [
  { to: 'mechanics', label: 'Team', shortLabel: 'Team', icon: Wrench },
  { to: 'analytics', label: 'Analytics', shortLabel: 'Analytics', icon: BarChart3 },
]

const sectionHeaderClass =
  'db-my-shop-nav-heading text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 border-b border-zinc-800/50 pb-2 flex items-center gap-3'

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
      {({ isActive }) => (
        <>
          <section.icon aria-hidden="true" className="h-4 w-4 shrink-0" />
          <span aria-hidden="true" className="db-my-shop-nav-label db-my-shop-nav-label-short whitespace-nowrap">
            {section.shortLabel}
          </span>
          <span aria-hidden="true" className="db-my-shop-nav-label db-my-shop-nav-label-full whitespace-nowrap">
            {section.label}
          </span>
          {isActive ? <ChevronRight aria-hidden="true" className="db-my-shop-nav-chevron ml-auto h-4 w-4" /> : null}
        </>
      )}
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
      <h2 className={sectionHeaderClass}>
        <Settings2 aria-hidden="true" className="h-3 w-3" />
        Shop
      </h2>
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
  const location = useLocation()
  const usesInternalDesktopScroll =
    location.pathname.startsWith('/dashboard/garage/services') ||
    location.pathname.startsWith('/dashboard/garage/inventory') ||
    location.pathname.startsWith('/dashboard/garage/purchasing')

  return (
    <div className="db-my-shop-workspace w-full flex-1 md:h-[calc(100dvh-9.25rem)] md:min-h-0 md:flex-none md:overflow-hidden">
      <div className="db-my-shop-layout">
        <GarageNav />

        <div
          className={`db-my-shop-content min-h-[400px] min-w-0 flex-1 scrollbar-dark md:min-h-0 ${
            usesInternalDesktopScroll ? 'md:overflow-hidden' : 'md:overflow-y-auto'
          }`}
        >
          <Routes>
            <Route index element={<Navigate to="mechanics" replace />} />
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
