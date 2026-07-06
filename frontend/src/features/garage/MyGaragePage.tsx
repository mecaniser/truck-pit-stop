import { NavLink, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { BarChart3, Boxes, ChevronRight, ClipboardList, Clock3, Settings2, Truck, User, Wrench, type LucideIcon } from 'lucide-react'
import ServicesManagementPage from '@/features/dashboard/ServicesManagementPage'
import InventoryPage from '@/features/inventory/InventoryPage'
import MechanicsPage from '@/features/mechanics/MechanicsPage'
import SuppliersPage from '@/features/suppliers/SuppliersPage'
import GarageAnalyticsPage from './GarageAnalyticsPage'
import LaborBookTimePage from './LaborBookTimePage'

type GarageSection = {
  to: string
  label: string
  shortLabel: string
  icon: LucideIcon
}

const GARAGE_SECTIONS: GarageSection[] = [
  { to: 'mechanics', label: 'Team', shortLabel: 'Team', icon: Wrench },
  { to: 'services', label: 'Services', shortLabel: 'Services', icon: ClipboardList },
  { to: 'labor-book-time', label: 'Labor Book Time', shortLabel: 'Book Time', icon: Clock3 },
  { to: 'inventory', label: 'Inventory', shortLabel: 'Inventory', icon: Boxes },
  { to: 'suppliers', label: 'Suppliers', shortLabel: 'Suppliers', icon: Truck },
  { to: 'analytics', label: 'Analytics', shortLabel: 'Analytics', icon: BarChart3 },
]

const staggeredReveal = (index: number) => ({
  animationDelay: `${index * 50}ms`,
})

const sectionHeaderClass =
  'text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 border-b border-zinc-800/50 pb-2 mb-6 flex items-center gap-3'

function MobileGarageNav() {
  return (
    <div className="lg:hidden">
      <div className="rounded-2xl border border-zinc-700/50 bg-zinc-900/80 p-2 backdrop-blur-sm">
        <nav className="flex gap-2 overflow-x-auto scrollbar-hide" style={{ WebkitOverflowScrolling: 'touch' }}>
          {GARAGE_SECTIONS.map((section, index) => (
            <NavLink
              key={section.to}
              to={section.to}
              style={staggeredReveal(index)}
              className={({ isActive }) =>
                `flex shrink-0 items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-xs font-medium transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
                  isActive
                    ? 'border-[var(--accent-400)]/50 bg-[var(--accent-600)] text-white shadow-lg shadow-[var(--accent-500)]/20'
                    : 'border-zinc-700/50 bg-zinc-800/60 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300'
                }`
              }
            >
              <section.icon className="h-4 w-4 shrink-0" />
              <span className="whitespace-nowrap">{section.shortLabel}</span>
            </NavLink>
          ))}
        </nav>
        <div className="mt-3 border-t border-zinc-800/60 px-1 pt-3">
          <NavLink
            to="/dashboard/settings"
            className="flex w-full items-center justify-between rounded-xl border border-zinc-700/50 bg-zinc-800/50 px-3 py-3 text-sm font-medium text-zinc-300 transition-all hover:border-zinc-600 hover:bg-zinc-800 hover:text-zinc-100"
          >
            <span className="flex items-center gap-3">
              <User className="h-4 w-4" />
              Profile & Settings
            </span>
            <ChevronRight className="h-4 w-4" />
          </NavLink>
        </div>
      </div>
    </div>
  )
}

function DesktopGarageNav() {
  return (
    <div className="hidden w-64 shrink-0 self-stretch lg:flex">
      <div className="flex h-full flex-1 flex-col rounded-2xl border border-zinc-700/50 bg-zinc-900/80 p-4 backdrop-blur-sm">
        <div className="flex-1">
          <h3 className={sectionHeaderClass}>
            <Settings2 className="h-3 w-3" />
            Garage
          </h3>
          <nav className="space-y-1">
            {GARAGE_SECTIONS.map((section, index) => (
              <NavLink
                key={section.to}
                to={section.to}
                style={staggeredReveal(index)}
                className={({ isActive }) =>
                  `flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition-all animate-[fadeIn_0.3s_ease-out_forwards] opacity-0 ${
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
            ))}
          </nav>
        </div>
        <div className="mt-6 border-t border-zinc-800/60 pt-6">
          <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.2em] text-zinc-500">
            Account
          </p>
          <NavLink
            to="/dashboard/settings"
            className="flex w-full items-center gap-3 rounded-xl border border-zinc-700/50 bg-zinc-800/50 px-3 py-3 text-sm font-medium text-zinc-300 transition-all hover:border-zinc-600 hover:bg-zinc-800 hover:text-zinc-100"
          >
            <User className="h-4 w-4" />
            Profile & Settings
            <ChevronRight className="ml-auto h-4 w-4" />
          </NavLink>
        </div>
      </div>
    </div>
  )
}

export default function MyGaragePage() {
  const location = useLocation()
  const usesInternalDesktopScroll =
    location.pathname.startsWith('/dashboard/garage/services') ||
    location.pathname.startsWith('/dashboard/garage/inventory')

  return (
    <div className="flex w-full flex-1 flex-col gap-6 lg:h-[calc(100vh-9.25rem)] lg:min-h-0 lg:flex-none lg:flex-row lg:items-stretch lg:overflow-hidden">
      <MobileGarageNav />
      <DesktopGarageNav />

      <div
        className={`min-h-[400px] flex-1 scrollbar-dark lg:min-h-0 ${
          usesInternalDesktopScroll ? 'lg:overflow-hidden' : 'lg:overflow-y-auto'
        }`}
      >
        <Routes>
          <Route index element={<Navigate to="mechanics" replace />} />
          <Route path="services" element={<ServicesManagementPage />} />
          <Route path="labor-book-time" element={<LaborBookTimePage />} />
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="mechanics" element={<MechanicsPage />} />
          <Route path="suppliers" element={<SuppliersPage />} />
          <Route path="analytics" element={<GarageAnalyticsPage />} />
        </Routes>
      </div>
    </div>
  )
}
