import type { ReactNode } from 'react'
import { format } from 'date-fns'

import type { RepairOrder, Vehicle } from '@/types'

export const portalColors = {
  violet: '#8b7cf7',
  green: '#3ecf6f',
  red: '#ff6b6e',
  amber: '#f0b959',
  vehicle: '#d9a521',
  teal: '#2dd4bf',
} as const

export function formatMoney(value: string | number | null | undefined) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(Number(value || 0))
}

export function orderTotal(order: RepairOrder) {
  const value = Number(order.total_cost || 0)
  return Number.isFinite(value) ? value : 0
}

export function daysOverdue(dueDate: string | null | undefined) {
  if (!dueDate) return 0
  const due = new Date(dueDate)
  const today = new Date()
  due.setHours(0, 0, 0, 0)
  today.setHours(0, 0, 0, 0)
  return Math.max(0, Math.floor((today.getTime() - due.getTime()) / 86_400_000))
}

export type OverdueLevel = 'none' | 'warn' | 'critical'

export function overdueLevel(days: number): OverdueLevel {
  if (days >= 3) return 'critical'
  if (days >= 1) return 'warn'
  return 'none'
}

export function vehicleName(vehicle: Vehicle | null | undefined) {
  if (!vehicle) return 'Vehicle'
  return [vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(' ')
}

export function vehicleMeta(vehicle: Vehicle | null | undefined) {
  if (!vehicle) return ''
  const parts = [
    vehicle.unit_number ? `Unit #${vehicle.unit_number}` : null,
    vehicle.license_plate ? `Plate ${vehicle.license_plate}` : null,
    vehicle.color,
  ]
  return parts.filter(Boolean).join(' · ')
}

export function Card({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-2xl border border-[#232939] bg-[#161a26] ${className}`}>
      {children}
    </section>
  )
}
export function SectionLabel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span className={`text-[11px] font-extrabold uppercase tracking-[0.1em] text-[#8b92a5] ${className}`}>
      {children}
    </span>
  )
}

export function Money({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return <span className={`whitespace-nowrap tabular-nums ${className}`}>{children}</span>
}

export function Pill({
  active = false,
  children,
  onClick,
}: {
  active?: boolean
  children: ReactNode
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-[34px] shrink-0 rounded-full border px-3.5 text-xs font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8b7cf7] ${
        active
          ? 'border-[#8b7cf7] bg-[#8b7cf7]/10 text-[#c9bfff]'
          : 'border-[#272d3d] bg-[#161a26] text-[#9aa1b3] hover:border-[#343b52] hover:text-white'
      }`}
    >
      {children}
    </button>
  )
}

export function DateBlock({ value }: { value: string | Date }) {
  const date = typeof value === 'string' ? new Date(value) : value
  return (
    <div className="flex h-[52px] w-[52px] shrink-0 flex-col items-center justify-center rounded-[11px] border border-[#272d3d] bg-[#12161f]">
      <span className="text-base font-extrabold leading-none tabular-nums text-[#eceef4]">{format(date, 'd')}</span>
      <span className="mt-1 text-[10px] font-bold uppercase text-[#5c6375]">{format(date, 'MMM')}</span>
    </div>
  )
}

export function PaidBadge() {
  return (
    <span className="rounded-md border border-[#3ecf6f]/30 bg-[#3ecf6f]/10 px-2 py-0.5 text-[10px] font-extrabold tracking-[0.06em] text-[#3ecf6f]">
      PAID
    </span>
  )
}
