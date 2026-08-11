import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Check, ChevronRight, CircleDollarSign, Clock3, Wrench } from 'lucide-react'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'

import { Spinner } from '@/components/ui'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type { Customer, Invoice, RepairOrder, Vehicle } from '@/types'

import {
  Card,
  formatMoney,
  isActiveRepair,
  Money,
  overdueLevel,
  daysOverdue,
  PaidBadge,
  repairStatusLabel,
  SectionLabel,
  vehicleMeta,
  vehicleName,
} from './portal-ui'

function orderVehicleLabel(order: RepairOrder) {
  const name = [order.vehicle_year, order.vehicle_make, order.vehicle_model].filter(Boolean).join(' ')
  return order.vehicle_unit_number ? `Unit #${order.vehicle_unit_number} · ${name}` : name || 'Vehicle'
}

async function getAll<T>(url: string) {
  const all: T[] = []
  let skip = 0
  while (true) {
    const response = await api.get(url, { params: { paginated: true, skip, limit: 100 } })
    const payload = response.data
    if (Array.isArray(payload)) return payload as T[]
    all.push(...payload.items)
    if (!payload.has_more || payload.items.length === 0) return all
    skip = payload.skip + payload.limit
  }
}

export default function PortalDashboardPage() {
  const user = useAuthStore(state => state.user)
  const [selecting, setSelecting] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const { data: customer } = useQuery<Customer>({
    queryKey: ['customer', user?.customer_id],
    queryFn: async () => (await api.get(`/customers/${user!.customer_id}`)).data,
    enabled: Boolean(user?.customer_id),
  })
  const { data: vehicles = [], isLoading: vehiclesLoading } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: () => getAll<Vehicle>('/vehicles'),
  })
  const { data: orders = [], isLoading: ordersLoading } = useQuery<RepairOrder[]>({
    queryKey: ['repair-orders'],
    queryFn: () => getAll<RepairOrder>('/repair-orders'),
  })
  const { data: invoices = [], isLoading: invoicesLoading } = useQuery<Invoice[]>({
    queryKey: ['customer-dashboard-invoices'],
    queryFn: async () => (await api.get('/invoices')).data,
  })

  const orderById = useMemo(
    () => new Map(orders.map(order => [order.id, order])),
    [orders],
  )
  const unpaid = useMemo(
    () => invoices
      .filter(invoice => !['paid', 'cancelled'].includes(invoice.status))
      .map(invoice => ({
        invoice,
        order: orderById.get(invoice.repair_order_id),
        overdueDays: daysOverdue(invoice.due_date),
      }))
      .sort((a, b) => b.overdueDays - a.overdueDays),
    [invoices, orderById],
  )
  const paidThisYear = useMemo(
    () => invoices.filter(invoice =>
      invoice.status === 'paid'
      && invoice.paid_at
      && new Date(invoice.paid_at).getFullYear() === new Date().getFullYear(),
    ),
    [invoices],
  )
  const recentlyPaid = useMemo(
    () => invoices
      .filter(invoice => invoice.status === 'paid')
      .sort((a, b) => new Date(b.paid_at || b.updated_at).getTime() - new Date(a.paid_at || a.updated_at).getTime())
      .slice(0, 3),
    [invoices],
  )
  const primaryVehicle = vehicles[0]
  const mileage = primaryVehicle?.mileage || 0
  const nextPm = mileage ? Math.ceil((mileage + 1) / 5000) * 5000 : 0
  const pmRemaining = nextPm ? Math.max(0, nextPm - mileage) : 0
  const activeRepairs = orders
    .filter(isActiveRepair)
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
  const quoteActions = activeRepairs.filter(order => order.quote_sent === true && order.quote_approved !== true)
  const actionCount = quoteActions.length + unpaid.length
  const balance = unpaid.reduce((sum, item) => sum + Number(item.invoice.total_amount || 0), 0)
  const paidYtd = paidThisYear.reduce((sum, invoice) => sum + Number(invoice.total_amount || 0), 0)
  const selected = unpaid.filter(item => selectedIds.includes(item.invoice.id))
  const selectedTotal = selected.reduce((sum, item) => sum + Number(item.invoice.total_amount || 0), 0)
  const oldest = unpaid[0]

  if (vehiclesLoading || ordersLoading || invoicesLoading) {
    return <div className="flex min-h-[420px] items-center justify-center"><Spinner size="xl" /></div>
  }

  const toggleInvoice = (id: string) => {
    setSelectedIds(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id])
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 xl:grid-cols-[1.4fr_1fr] xl:gap-3.5">
        <Card className={unpaid.some(item => item.overdueDays > 0) ? 'border-[#ff6b6e]/30 p-5 sm:p-[22px]' : 'p-5 sm:p-[22px]'}>
          {balance > 0 ? (
            <>
              <div className="flex items-center gap-2">
                <span className="h-[7px] w-[7px] rounded-full bg-[#ff6b6e]" />
                <SectionLabel className="text-[#ff8b8d]">
                  Balance due{unpaid.every(item => item.overdueDays > 0) ? ' · all past due' : ''}
                </SectionLabel>
              </div>
              <div className="mt-2 flex flex-wrap items-end gap-x-3 gap-y-1">
                <Money className="text-[36px] font-extrabold leading-none tracking-[-0.02em] sm:text-[42px]">
                  {formatMoney(balance)}
                </Money>
                <span className="pb-1 text-[13px] text-[#8b92a5]">across {unpaid.length} invoice{unpaid.length === 1 ? '' : 's'}</span>
              </div>
              <p className="mt-2 text-xs text-[#9aa1b3]">
                {oldest?.overdueDays
                  ? `Oldest unpaid: ${oldest.overdueDays} day${oldest.overdueDays === 1 ? '' : 's'} past due${oldest.invoice.due_date ? ` · ${format(new Date(oldest.invoice.due_date), 'MMM d')}` : ''}`
                  : 'Your balance is current.'}
              </p>
              <div className="mt-5 grid gap-2 sm:flex">
                {oldest && (
                  <Link
                    to={`/portal/invoices/${oldest.invoice.id}`}
                    state={{ paymentOrigin: 'Dashboard', invoiceQueue: unpaid.map(item => item.invoice.id) }}
                    className="flex h-[46px] items-center justify-center rounded-xl bg-[#8b7cf7] px-5 text-sm font-extrabold text-[#0e1118] hover:brightness-110"
                  >
                    Pay invoices — {formatMoney(balance)}
                  </Link>
                )}
                {oldest && unpaid.length > 1 && (
                  <Link
                    to={`/portal/invoices/${oldest.invoice.id}`}
                    state={{ paymentOrigin: 'Dashboard' }}
                    className="flex h-[46px] items-center justify-center rounded-xl border border-[#272d3d] bg-[#191d2a] px-5 text-sm font-bold text-[#c9cdd8] hover:border-[#343b52]"
                  >
                    Pay oldest first
                  </Link>
                )}
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 text-[#3ecf6f]">
                <Check className="h-4 w-4" />
                <SectionLabel className="text-[#3ecf6f]">All paid up</SectionLabel>
              </div>
              <Money className="mt-2 block text-[36px] font-extrabold tracking-[-0.02em] sm:text-[42px]">$0.00</Money>
              <p className="mt-1 text-xs text-[#9aa1b3]">{pmRemaining ? `Next PM due in about ${pmRemaining.toLocaleString()} miles.` : 'No outstanding invoices.'}</p>
              <Link to="/portal/services" className="mt-5 inline-flex h-[46px] items-center justify-center rounded-xl border border-[#272d3d] bg-[#191d2a] px-5 text-sm font-bold text-[#c9cdd8]">
                Book a service
              </Link>
            </>
          )}
        </Card>

        <div className="grid grid-cols-2 gap-2.5">
          {[
            {
              label: 'My truck',
              value: primaryVehicle ? vehicleName(primaryVehicle).replace(/^\d{4}\s/, '') : 'No vehicle',
              meta: primaryVehicle ? `${vehicleMeta(primaryVehicle).split(' · ')[0] || 'Vehicle'}${mileage ? ` · ${mileage.toLocaleString()} mi` : ''}` : 'Add your first truck',
              valueClass: 'text-[#eceef4]',
              metaClass: 'text-[#d9a521]',
            },
            {
              label: 'Next PM due',
              value: pmRemaining ? `in ${pmRemaining.toLocaleString()} mi` : 'Not scheduled',
              meta: nextPm ? `Level A · ~${nextPm.toLocaleString()}` : 'Add current mileage',
              valueClass: 'text-[#f0b959]',
              metaClass: 'text-[#8b92a5]',
            },
            {
              label: 'In the shop',
              value: activeRepairs.length ? `${activeRepairs.length} active` : 'Nothing today',
              meta: `${activeRepairs.length} active repair${activeRepairs.length === 1 ? '' : 's'}`,
              valueClass: 'text-[#eceef4]',
              metaClass: 'text-[#8b92a5]',
            },
            {
              label: 'Paid YTD',
              value: formatMoney(paidYtd),
              meta: `${paidThisYear.length} of ${orders.length} orders`,
              valueClass: 'text-[#3ecf6f]',
              metaClass: 'text-[#8b92a5]',
            },
          ].map(tile => {
            const card = (
              <Card className={`flex min-h-[112px] flex-col justify-between rounded-[14px] p-3.5 sm:p-4 ${
                tile.label === 'In the shop' ? 'transition-colors group-hover:border-[#8b7cf7]/60 group-hover:bg-[#1a1e2b]' : ''
              }`}>
                <SectionLabel className="text-[10px]">{tile.label}</SectionLabel>
                <div>
                  <div className={`truncate text-sm font-extrabold ${tile.valueClass}`}>{tile.value}</div>
                  <div className={`mt-1 truncate text-[11px] ${tile.metaClass}`}>{tile.meta}</div>
                </div>
              </Card>
            )

            return tile.label === 'In the shop' ? (
              <Link
                key={tile.label}
                to="/portal/repairs?view=active"
                className="group rounded-[14px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8b7cf7]"
                aria-label={`View ${activeRepairs.length} active repair${activeRepairs.length === 1 ? '' : 's'}`}
              >
                {card}
              </Link>
            ) : <div key={tile.label}>{card}</div>
          })}
        </div>
      </div>

      {actionCount > 0 && (
        <Card className="overflow-hidden border-[#f0b959]/30">
          <div className="flex items-center justify-between gap-3 border-b border-[#1e2432] px-4 py-[15px] sm:px-[18px]">
            <div className="flex min-w-0 items-center gap-2.5">
              <AlertTriangle className="h-4 w-4 shrink-0 text-[#f0b959]" />
              <SectionLabel className="truncate text-[#f0b959]">Action required</SectionLabel>
              <span className="rounded-full bg-[#f0b959]/10 px-2 py-0.5 text-[10px] font-extrabold text-[#f0b959]">
                {actionCount}
              </span>
            </div>
            <span className="hidden text-xs text-[#8b92a5] sm:inline">Review these items to keep work moving</span>
          </div>
          <div className="space-y-2 p-2.5">
            {quoteActions.map(order => (
              <Link
                key={`quote-${order.id}`}
                to="/portal/repairs?view=active"
                state={{ selectedOrderId: order.id }}
                className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-xl border border-[#f0b959]/20 bg-[#f0b959]/5 px-3.5 py-3 hover:border-[#f0b959]/40 sm:grid-cols-[210px_1fr_auto]"
              >
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-extrabold">Estimate awaiting approval</p>
                  <p className="mt-0.5 truncate text-[11px] text-[#8b92a5]">{order.order_number} · {orderVehicleLabel(order)}</p>
                </div>
                <span className="hidden truncate text-xs text-[#9aa1b3] sm:block">{order.description || 'Repair estimate is ready for review'}</span>
                <span className="inline-flex h-[34px] items-center justify-center rounded-lg bg-[#8b7cf7] px-3.5 text-xs font-extrabold text-[#0e1118]">
                  Review estimate
                </span>
              </Link>
            ))}
            {unpaid.map(({ invoice, order, overdueDays }) => (
              <Link
                key={`payment-${invoice.id}`}
                to={`/portal/invoices/${invoice.id}`}
                state={{ paymentOrigin: 'Dashboard' }}
                className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-xl border border-[#ff6b6e]/20 bg-[#ff6b6e]/5 px-3.5 py-3 hover:border-[#ff6b6e]/40 sm:grid-cols-[210px_1fr_auto_auto]"
              >
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-extrabold">{overdueDays > 0 ? 'Past-due invoice' : 'Invoice ready to pay'}</p>
                  <p className="mt-0.5 truncate text-[11px] text-[#8b92a5]">{order?.order_number || invoice.invoice_number} · {order ? orderVehicleLabel(order) : 'Repair service'}</p>
                </div>
                <span className="hidden truncate text-xs text-[#9aa1b3] sm:block">
                  {overdueDays > 0 ? `${overdueDays} day${overdueDays === 1 ? '' : 's'} past due` : 'Payment due'}
                </span>
                <Money className="hidden text-sm font-extrabold sm:block">{formatMoney(invoice.total_amount)}</Money>
                <span className="inline-flex h-[34px] items-center justify-center rounded-lg bg-[#8b7cf7] px-4 text-xs font-extrabold text-[#0e1118]">
                  Pay
                </span>
              </Link>
            ))}
          </div>
        </Card>
      )}

      {activeRepairs.length > 0 && (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-[#1e2432] px-4 py-[15px] sm:px-[18px]">
            <div className="flex min-w-0 items-center gap-2.5">
              <Wrench className="h-4 w-4 shrink-0 text-[#a78bfa]" />
              <SectionLabel className="truncate text-[#eceef4]">Active repairs</SectionLabel>
              <span className="text-xs font-extrabold text-[#a78bfa]">{activeRepairs.length}</span>
            </div>
            <Link to="/portal/repairs?view=active" className="inline-flex min-h-[44px] items-center text-xs font-bold text-[#a78bfa] hover:text-[#c4b1ff]">
              View all <ChevronRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          <div className="space-y-2 p-2.5">
            {activeRepairs.slice(0, 4).map(order => (
              <Link
                key={order.id}
                to="/portal/repairs?view=active"
                state={{ selectedOrderId: order.id }}
                className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-xl border border-[#1e2432] bg-[#12161f] px-3.5 py-3 hover:border-[#343b52] hover:bg-[#161b26] sm:grid-cols-[210px_1fr_auto_auto]"
              >
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-extrabold">{order.description || 'Repair service'}</p>
                  <p className="mt-0.5 truncate text-[11px] text-[#8b92a5]">{order.order_number} · {orderVehicleLabel(order)}</p>
                </div>
                <div className="hidden min-w-0 items-center gap-1.5 text-xs text-[#9aa1b3] sm:flex">
                  <Clock3 className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">Updated {format(new Date(order.updated_at), 'MMM d · h:mm a')}</span>
                </div>
                <span className={`rounded-md border px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.04em] ${
                  order.status === 'invoiced'
                    ? 'border-[#ff6b6e]/30 bg-[#ff6b6e]/10 text-[#ff8b8d]'
                    : order.quote_sent && !order.quote_approved
                      ? 'border-[#f0b959]/30 bg-[#f0b959]/10 text-[#f0b959]'
                      : 'border-[#8b7cf7]/30 bg-[#8b7cf7]/10 text-[#c9bfff]'
                }`}>
                  {repairStatusLabel(order.status)}
                </span>
                <ChevronRight className="hidden h-4 w-4 text-[#5c6375] sm:block" />
              </Link>
            ))}
          </div>
        </Card>
      )}

      {unpaid.length > 0 && (
        <Card className="overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-[#1e2432] p-4 sm:flex-row sm:items-center sm:justify-between sm:px-[18px] sm:py-[15px]">
            <div className="flex items-baseline gap-2.5">
              <SectionLabel className="text-[#eceef4]">Unpaid invoices</SectionLabel>
              <span className="text-xs font-extrabold text-[#ff8b8d]">{unpaid.filter(item => item.overdueDays > 0).length} past due</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="hidden text-xs text-[#8b92a5] sm:inline">Sorted by days overdue</span>
              {selecting && selected.length > 0 && (
                <Link
                  to={`/portal/invoices/${selected[0].invoice.id}`}
                  state={{ paymentOrigin: 'Dashboard', invoiceQueue: selected.map(item => item.invoice.id) }}
                  className="inline-flex h-[44px] items-center rounded-lg bg-[#8b7cf7] px-3.5 text-xs font-extrabold text-[#0e1118] sm:h-[34px]"
                >
                  Pay {selected.length} · {formatMoney(selectedTotal)}
                </Link>
              )}
              <button
                type="button"
                onClick={() => {
                  setSelecting(current => !current)
                  setSelectedIds([])
                }}
                className="h-[44px] rounded-lg border border-[#8b7cf7] bg-[#8b7cf7]/10 px-3.5 text-xs font-extrabold text-[#c9bfff] sm:h-[34px]"
              >
                {selecting ? 'Done' : 'Select & pay'}
              </button>
            </div>
          </div>
          <div className="space-y-1.5 p-2.5">
            {unpaid.map(({ invoice, order, overdueDays }) => {
              const level = overdueLevel(overdueDays)
              const isSelected = selectedIds.includes(invoice.id)
              return (
                <div key={invoice.id} className="relative overflow-hidden rounded-[11px] border border-[#1e2432] bg-[#12161f] hover:border-[#343b52] hover:bg-[#161b26]">
                  {level !== 'none' && <span className={`absolute inset-y-0 left-0 w-1 ${level === 'critical' ? 'bg-[#ff6b6e]' : 'bg-[#f0b959]'}`} />}
                  <div className="grid grid-cols-[auto_1fr_auto] items-center gap-3 px-3 py-3 pl-4 sm:grid-cols-[auto_210px_1fr_84px_auto] sm:px-3.5 sm:py-2.5 sm:pl-[18px]">
                    {selecting && (
                      <button
                        type="button"
                        aria-label={`${isSelected ? 'Deselect' : 'Select'} invoice ${invoice.invoice_number}`}
                        onClick={() => toggleInvoice(invoice.id)}
                        className={`flex h-5 w-5 items-center justify-center rounded border ${isSelected ? 'border-[#8b7cf7] bg-[#8b7cf7] text-[#0e1118]' : 'border-[#343b52]'}`}
                      >
                        {isSelected && <Check className="h-3.5 w-3.5" />}
                      </button>
                    )}
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-bold">{order?.order_number || invoice.invoice_number}</p>
                      <p className="mt-0.5 truncate text-[11px] text-[#8b92a5]">{order?.description || `Invoice ${invoice.invoice_number}`}</p>
                    </div>
                    <div className="col-span-2 flex items-center justify-between gap-2 sm:col-span-1 sm:block">
                      <span className={`rounded-md px-2 py-1 text-[11px] font-extrabold ${
                        level === 'critical'
                          ? 'border border-[#ff6b6e]/30 bg-[#ff6b6e]/10 text-[#ff8b8d]'
                          : level === 'warn'
                            ? 'bg-[#f0b959]/10 text-[#f0b959]'
                            : 'bg-[#191d2a] text-[#8b92a5]'
                      }`}>
                        {overdueDays ? `${overdueDays} day${overdueDays === 1 ? '' : 's'} past due` : 'Due soon'}
                      </span>
                    </div>
                    <Money className="text-right text-sm font-extrabold">{formatMoney(invoice.total_amount)}</Money>
                    {!selecting && (
                      <Link
                        to={`/portal/invoices/${invoice.id}`}
                        state={{ paymentOrigin: 'Dashboard' }}
                        className="flex h-[44px] items-center justify-center rounded-lg bg-[#8b7cf7] px-4 text-xs font-extrabold text-[#0e1118] sm:h-[34px]"
                      >
                        Pay
                      </Link>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {recentlyPaid.length > 0 && (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-[#1e2432] px-[18px] py-[15px]">
            <SectionLabel className="text-[#eceef4]">Recently paid</SectionLabel>
            <Link to="/portal/repairs" className="inline-flex min-h-[44px] items-center text-xs font-bold text-[#a78bfa] hover:text-[#c4b1ff]">
              View all history <ChevronRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          <div className="space-y-1.5 p-2.5">
            {recentlyPaid.map(invoice => {
              const order = orderById.get(invoice.repair_order_id)
              return (
                <div key={invoice.id} className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-[11px] border border-[#1e2432] bg-[#12161f] px-3.5 py-2.5 sm:grid-cols-[210px_1fr_auto_84px]">
                  <span className="truncate text-[13px] font-bold">{order?.order_number || invoice.invoice_number}</span>
                  <span className="hidden truncate text-xs text-[#8b92a5] sm:block">{order?.description || 'Repair service'}</span>
                  <PaidBadge />
                  <Money className="text-right text-sm font-extrabold">{formatMoney(invoice.total_amount)}</Money>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {!customer && (
        <div className="sr-only" aria-live="polite"><CircleDollarSign /> Account data is loading</div>
      )}
    </div>
  )
}
