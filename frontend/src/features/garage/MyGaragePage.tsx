import { NavLink, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { BarChart3, Boxes, ChevronRight, ClipboardList, Clock3, Settings2, ShoppingCart, Wrench, type LucideIcon } from 'lucide-react'
import ServicesManagementPage from '@/features/dashboard/ServicesManagementPage'
import InventoryPage from '@/features/inventory/InventoryPage'
import PurchasingWorkspace from '@/features/inventory/PurchasingWorkspace'
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

const staggeredReveal = (index: number) => ({
  animationDelay: `${index * 50}ms`,
})

const sectionHeaderClass =
  'text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 border-b border-zinc-800/50 pb-2 mb-6 flex items-center gap-3'

function MobileGarageLinks({ sections, offset = 0 }: { sections: GarageSection[]; offset?: number }) {
  return sections.map((section, index) => (
    <NavLink
      key={section.to}
      to={section.to}
      style={staggeredReveal(index + offset)}
      className={({ isActive }) =>
        `db-my-shop-nav-item flex min-h-11 items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-xs font-medium transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
          isActive
            ? 'border-[var(--accent-400)]/50 bg-[var(--accent-600)] text-white shadow-lg shadow-[var(--accent-500)]/20'
            : 'border-zinc-700/50 bg-zinc-800/60 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300'
        }`
      }
    >
      <section.icon className="h-4 w-4 shrink-0" />
      <span className="whitespace-nowrap">{section.shortLabel}</span>
    </NavLink>
  ))
}

function MobileGarageNav() {
  return (
    <div className="lg:hidden">
      <div className="rounded-2xl border border-zinc-700/50 bg-zinc-900/80 p-2 backdrop-blur-sm">
        <nav aria-label="Shop sections" className="flex flex-col gap-3">
          <div
            role="group"
            aria-label="Shop operations"
            data-shop-menu-cluster="operational"
            className="grid grid-cols-2 gap-2 sm:grid-cols-4"
          >
            <MobileGarageLinks sections={OPERATIONAL_SECTIONS} />
          </div>
          <div className="border-t border-zinc-700/50 pt-3">
            <div
              role="group"
              aria-label="Shop administration and insights"
              data-shop-menu-cluster="secondary"
              className="grid grid-cols-2 gap-2"
            >
              <MobileGarageLinks sections={SECONDARY_SECTIONS} offset={OPERATIONAL_SECTIONS.length} />
            </div>
          </div>
        </nav>
      </div>
    </div>
  )
}

function DesktopGarageLinks({ sections, offset = 0 }: { sections: GarageSection[]; offset?: number }) {
  return sections.map((section, index) => (
    <NavLink
      key={section.to}
      to={section.to}
      style={staggeredReveal(index + offset)}
      className={({ isActive }) =>
        `db-my-shop-nav-item flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
          isActive
            ? 'border border-[var(--accent-500)]/30 bg-[var(--accent-500)]/10 text-[var(--accent-400)]'
            : 'border border-transparent text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-300'
        }`
      }
    >
      {({ isActive }) => (
        <>
          <section.icon className="h-4 w-4" />
          {section.label}
          {isActive ? <ChevronRight className="ml-auto h-4 w-4" /> : null}
        </>
      )}
    </NavLink>
  ))
}

function DesktopGarageNav() {
  return (
    <div className="hidden w-64 shrink-0 self-stretch lg:flex">
      <div className="flex h-full flex-1 flex-col rounded-2xl border border-zinc-700/50 bg-zinc-900/80 p-4 backdrop-blur-sm">
        <h3 className={sectionHeaderClass}>
          <Settings2 className="h-3 w-3" />
          Shop
        </h3>
        <nav aria-label="Shop sections" className="flex min-h-0 flex-1 flex-col overflow-y-auto scrollbar-dark">
          <div role="group" aria-label="Shop operations" data-shop-menu-cluster="operational" className="space-y-1">
            <DesktopGarageLinks sections={OPERATIONAL_SECTIONS} />
          </div>
          <div className="mt-auto border-t border-zinc-700/50 pt-3">
            <div
              role="group"
              aria-label="Shop administration and insights"
              data-shop-menu-cluster="secondary"
              className="space-y-1"
            >
              <DesktopGarageLinks sections={SECONDARY_SECTIONS} offset={OPERATIONAL_SECTIONS.length} />
            </div>
          </div>
        </nav>
      </div>
    </div>
  )
}

export default function MyGaragePage() {
  const location = useLocation()
  const usesInternalDesktopScroll =
    location.pathname.startsWith('/dashboard/garage/services') ||
    location.pathname.startsWith('/dashboard/garage/inventory') ||
    location.pathname.startsWith('/dashboard/garage/purchasing')

  return (
    <div className="db-my-shop-workspace flex w-full flex-1 flex-col gap-6 md:h-[calc(100dvh-9.25rem)] md:min-h-0 md:flex-none md:overflow-hidden lg:flex-row lg:items-stretch">
      <MobileGarageNav />
      <DesktopGarageNav />

      <div
        className={`min-h-[400px] flex-1 scrollbar-dark md:min-h-0 lg:pl-1.5 lg:pt-1.5 ${
          usesInternalDesktopScroll ? 'md:overflow-hidden' : 'md:overflow-y-auto'
        }`}
      >
        <Routes>
          <Route index element={<Navigate to="mechanics" replace />} />
          <Route path="services" element={<ServicesManagementPage />} />
          <Route path="labor-book-time" element={<LaborBookTimePage />} />
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="purchasing" element={<PurchasingWorkspace />} />
          <Route path="mechanics" element={<MechanicsPage />} />
          <Route path="suppliers" element={<Navigate to="/dashboard/garage/purchasing?view=suppliers" replace />} />
          <Route path="reviews" element={<GoogleReviewsPage />} />
          <Route path="reviews/settings" element={<GoogleReviewsSettingsPage />} />
          <Route path="analytics" element={<GarageAnalyticsPage />} />
        </Routes>
      </div>
    </div>
  )
}
