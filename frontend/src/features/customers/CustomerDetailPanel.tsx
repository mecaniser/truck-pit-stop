import React, { type ReactNode } from 'react'
import type { ViewMode } from '@/components/ViewToggle'
import type { LucideIcon } from 'lucide-react'
import {
  DollarSign, Mail, Pencil, Phone, Plus, Search, Star, Trash2, Truck, User, Wrench, X,
} from 'lucide-react'

import { LoadingLine } from '@/components/ui'
import ViewToggle from '@/components/ViewToggle'
import { formatUSPhone } from '@/utils/phone'
import { vehicleDisplayLabel } from '@/lib/vehicleName'
import type { Customer, Vehicle } from '@/types'
import {
  balanceAmountLabel,
  balanceLabel,
  balanceLabelClass,
  formatCustomerSource,
  numericBalance,
  stripRegNumber,
} from './customerDetailFormat'
import type { CustomerHistoryResponse } from './customerDetailFormat'

/**
 * A customer's record: summary, contacts, notes, trucks, and service history.
 *
 * This was 714 lines in the middle of a ternary inside CustomersPage. The
 * repair-order workspace needs the same view — an operator looking at a job
 * should be able to see who the carrier is and what they owe without leaving
 * the order — and a second copy would have drifted from this one within a
 * release. The props are broad because the view genuinely reads that much;
 * they are passed rather than fetched so each host keeps ownership of its own
 * queries and modals.
 */
export type CustomerDetailPanelProps = {
  selectedCustomer: Customer
  detailTab: 'overview' | 'history'
  setDetailTab: (tab: 'overview' | 'history') => void
  expandedHistoryId: string | null
  setExpandedHistoryId: (id: string | null) => void
  HistoryRoDetail: (props: { customerId: string; orderId: string }) => ReactNode

  customerVehicles?: Vehicle[]
  customerContacts?: any[]
  customerHistory?: CustomerHistoryResponse | null
  isLoadingVehicles?: boolean
  isLoadingContacts?: boolean
  isLoadingHistory?: boolean

  ownedVehicles: Vehicle[]
  authorityVehicles: Vehicle[]
  visibleCustomerVehicleGroups: {
    key: string
    title: string
    description: string
    vehicles: Vehicle[]
    visibleVehicles: Vehicle[]
    icon: LucideIcon
  }[]
  vehicleCount: number
  visibleVehicleCount: number
  vehicleTableColumnCount: number
  vehicleRelationshipNote: (vehicle: Vehicle, groupKey: string) => ReactNode
  shouldShowVehicleSearch: boolean
  showVehicleUnitColumn: boolean
  showVehicleVinColumn: boolean
  showVehiclePlateColumn: boolean

  vehiclesViewMode: ViewMode
  setVehiclesViewMode: (mode: ViewMode) => void
  vehicleRelationshipSearch: string
  setVehicleRelationshipSearch: (value: string) => void
  vehicleRelationshipFilter: 'all' | 'owned' | 'authority'
  setVehicleRelationshipFilter: (value: 'all' | 'owned' | 'authority') => void
  setSelectedVehicleInPanel: (vehicle: Vehicle | null) => void

  openAddContactModal: () => void
  openEditContactModal: (contact: any) => void
  handleDeleteContactClick: (contact: any) => void
  openAddVehicleModal: () => void
  openEditVehicleModal: (vehicle: Vehicle) => void
  handleDeleteVehicleClick: (vehicle: Vehicle) => void
}

export default function CustomerDetailPanel({
  selectedCustomer,
  detailTab,
  setDetailTab,
  expandedHistoryId,
  setExpandedHistoryId,
  HistoryRoDetail,
  customerVehicles,
  customerContacts,
  customerHistory,
  isLoadingVehicles,
  isLoadingContacts,
  isLoadingHistory,
  ownedVehicles,
  authorityVehicles,
  visibleCustomerVehicleGroups,
  vehicleCount,
  visibleVehicleCount,
  vehicleTableColumnCount,
  vehicleRelationshipNote,
  shouldShowVehicleSearch,
  showVehicleUnitColumn,
  showVehicleVinColumn,
  showVehiclePlateColumn,
  vehiclesViewMode,
  setVehiclesViewMode,
  vehicleRelationshipSearch,
  setVehicleRelationshipSearch,
  vehicleRelationshipFilter,
  setVehicleRelationshipFilter,
  setSelectedVehicleInPanel,
  openAddContactModal,
  openEditContactModal,
  handleDeleteContactClick,
  openAddVehicleModal,
  openEditVehicleModal,
  handleDeleteVehicleClick,
}: CustomerDetailPanelProps) {
  return (
    <div className="p-6 space-y-6">
      {/* Tabs */}
      <div className="flex border-b border-gray-200 -mt-2">
        <button
          type="button"
          onClick={() => setDetailTab('overview')}
          className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
            detailTab === 'overview'
              ? 'border-amber-500 text-amber-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Overview
        </button>
        <button
          type="button"
          onClick={() => setDetailTab('history')}
          className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
            detailTab === 'history'
              ? 'border-amber-500 text-amber-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          History
        </button>
      </div>

      {detailTab === 'history' ? (
        <div className="space-y-6">
          {/* Lifetime stats */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-gray-900">
                {isLoadingHistory ? '—' : customerHistory?.stats.completed_orders ?? 0}
              </p>
              <p className="text-xs text-gray-500">Completed ROs</p>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-gray-900">
                {isLoadingHistory ? '—' : `$${parseFloat(customerHistory?.stats.lifetime_spend || '0').toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
              </p>
              <p className="text-xs text-gray-500">Lifetime spend</p>
            </div>
            <div className="bg-emerald-50 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-emerald-700">
                {isLoadingHistory ? '—' : `$${parseFloat(customerHistory?.stats.lifetime_savings || '0').toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
              </p>
              <p className="text-xs text-emerald-700/80">Total saved</p>
            </div>
          </div>

          {/* RO list */}
          <div>
            <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Repair Orders</h3>
            {isLoadingHistory ? (
              <LoadingLine className="text-gray-400">Loading…</LoadingLine>
            ) : !customerHistory?.items.length ? (
              <div className="bg-gray-50 rounded-xl p-6 text-center border border-gray-100">
                <Wrench className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                <p className="text-sm text-gray-500">No repair orders yet</p>
              </div>
            ) : (
              <div className="bg-gray-50 rounded-xl border border-gray-100 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-100 text-gray-600 text-xs uppercase tracking-wider">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">RO</th>
                      <th className="px-3 py-2 text-left font-medium">Vehicle</th>
                      <th className="px-3 py-2 text-left font-medium">Status</th>
                      <th className="px-3 py-2 text-right font-medium">Saved</th>
                      <th className="px-3 py-2 text-right font-medium">Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {customerHistory.items.map((ro) => {
                      const dateStr = ro.work_completed_at || ro.created_at
                      const dateFmt = dateStr ? new Date(dateStr).toLocaleDateString() : '—'
                      const saving = parseFloat(ro.savings || '0')
                      const isExpanded = expandedHistoryId === ro.id
                      return (
                        <React.Fragment key={ro.id}>
                          <tr
                            onClick={() => setExpandedHistoryId(isExpanded ? null : ro.id)}
                            className={`hover:bg-gray-100/50 cursor-pointer ${isExpanded ? 'bg-amber-50/40' : ''}`}
                          >
                            <td className="px-3 py-2.5 text-gray-900 font-medium">
                              <span className="inline-flex items-center gap-1">
                                <span className={`text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`}>›</span>
                                {ro.order_number}
                              </span>
                              <div className="text-[11px] text-gray-500 font-normal ml-3">{dateFmt}</div>
                            </td>
                            <td className="px-3 py-2.5 text-gray-700">
                              {vehicleDisplayLabel({
                                year: ro.vehicle_year,
                                make: ro.vehicle_make,
                                model: ro.vehicle_model,
                                unit_number: ro.vehicle_unit_number,
                              })}
                              {ro.vehicle_unit_number && (
                                <div className="text-[11px] text-gray-500">#{ro.vehicle_unit_number}</div>
                              )}
                            </td>
                            <td className="px-3 py-2.5">
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-200 text-gray-700 capitalize">
                                {ro.status.replace('_', ' ')}
                              </span>
                            </td>
                            <td className="px-3 py-2.5 text-right">
                              {saving > 0 ? (
                                <span className="text-emerald-600 font-medium">−${saving.toFixed(2)}</span>
                              ) : (
                                <span className="text-gray-300">—</span>
                              )}
                            </td>
                            <td className="px-3 py-2.5 text-right text-gray-900 font-semibold">
                              ${parseFloat(ro.total_cost).toFixed(2)}
                            </td>
                          </tr>
                          {isExpanded && selectedCustomer && (
                            <tr className="bg-white">
                              <td colSpan={5} className="px-4 py-3 border-t border-amber-100">
                                <HistoryRoDetail customerId={selectedCustomer.id} orderId={ro.id} />
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : (
      <>
      {/* Summary row: Contact, US DOT, MC Number, Address, Customer Since,
          Balance — the at-a-glance facts about this company, laid out as a
          row of small stat blocks (matches the source system's layout). */}
      <div>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Summary</h3>
        <div className="bg-gray-50 rounded-xl p-4 grid grid-cols-2 sm:grid-cols-3 gap-4">
          {(() => {
            const namedContacts = (customerContacts || []).filter((c) => c.first_name || c.last_name)
            const askFor = namedContacts.find((c) => c.is_primary) || namedContacts[0]
            const askForName = askFor ? [askFor.first_name, askFor.last_name].filter(Boolean).join(' ') : null
            return (
              <div>
                <p className="text-xs text-gray-500">Contact</p>
                {askForName ? (
                  <>
                    <p className="text-gray-900 font-medium">{askForName}</p>
                    {askFor?.phone && (
                      <a href={`tel:${askFor.phone}`} className="text-xs text-gray-500 hover:text-amber-600 block">
                        {formatUSPhone(askFor.phone)}
                      </a>
                    )}
                  </>
                ) : (
                  <>
                    {selectedCustomer.phone && (
                      <a href={`tel:${selectedCustomer.phone}`} className="text-gray-900 hover:text-amber-600 font-medium block">
                        {formatUSPhone(selectedCustomer.phone)}
                      </a>
                    )}
                    <a href={`mailto:${selectedCustomer.email}`} className="text-xs text-gray-500 hover:text-amber-600 block">
                      {selectedCustomer.email}
                    </a>
                  </>
                )}
              </div>
            )
          })()}

          <div>
            <p className="text-xs text-gray-500">US DOT</p>
            <p className="text-gray-900 font-medium">{stripRegNumber(selectedCustomer.usdot_number) || '—'}</p>
          </div>

          <div>
            <p className="text-xs text-gray-500">MC Number</p>
            <p className="text-gray-900 font-medium">{stripRegNumber(selectedCustomer.mc_number) || '—'}</p>
          </div>

          <div>
            <p className="text-xs text-gray-500">Address</p>
            {selectedCustomer.billing_address_line1 || selectedCustomer.billing_city ? (
              <div className="text-gray-900 text-sm">
                {selectedCustomer.billing_address_line1 && <p>{selectedCustomer.billing_address_line1}</p>}
                <p>
                  {[selectedCustomer.billing_city, selectedCustomer.billing_state, selectedCustomer.billing_zip]
                    .filter(Boolean)
                    .join(', ')}
                </p>
              </div>
            ) : (
              <p className="text-gray-900 font-medium">—</p>
            )}
          </div>

          <div>
            <p className="text-xs text-gray-500">Customer Since</p>
            <p className="text-gray-900 font-medium">
              {new Date(selectedCustomer.created_at).toLocaleDateString()}
            </p>
          </div>

          <div>
            <p className="text-xs text-gray-500">
              {numericBalance(selectedCustomer.balance) > 0 ? 'Balance due' : numericBalance(selectedCustomer.balance) < 0 ? 'Account credit' : 'Balance'}
            </p>
            <p className={`font-semibold ${balanceLabelClass(selectedCustomer.balance)}`}>
              {selectedCustomer.balance !== undefined
                ? balanceAmountLabel(selectedCustomer.balance)
                : '—'}
            </p>
          </div>

          {selectedCustomer.source && (
            <div>
              <p className="text-xs text-gray-500">Source</p>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                {formatCustomerSource(selectedCustomer.source)}
              </span>
            </div>
          )}

          <div>
            <p className="text-xs text-gray-500">QuickBooks</p>
            {selectedCustomer.quickbooks_customer_id ? (
              <span className="inline-flex items-center gap-1 text-emerald-700 text-sm font-medium">
                ✓ Linked
              </span>
            ) : (
              <span className="text-gray-400 text-sm">Not linked</span>
            )}
          </div>
        </div>
      </div>

      {/* Contacts: named individuals at this company (dispatcher, owner,
          driver). The auto-created "Main Line" placeholder (no name, just
          mirrors the company's own email/phone shown above) is filtered out. */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Contacts</h3>
          <div className="flex items-center gap-2">
            {isLoadingContacts && <span className="text-xs text-gray-400">Loading...</span>}
            <button
              onClick={openAddContactModal}
              className="px-3 py-1.5 text-xs font-medium text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-lg transition-colors flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Contact
            </button>
          </div>
        </div>
        {(() => {
          const namedContacts = (customerContacts || []).filter((c) => c.first_name || c.last_name)
          if (namedContacts.length === 0) {
            return (
              <div className="bg-gray-50 rounded-xl p-4 text-sm text-gray-500 text-center">
                No named contacts yet — using the company's own email/phone above.
              </div>
            )
          }
          return (
            <div className="bg-gray-50 rounded-xl border border-gray-100 overflow-hidden divide-y divide-gray-100">
              {namedContacts.map((contact) => {
                const name = [contact.first_name, contact.last_name].filter(Boolean).join(' ')
                return (
                  <div key={contact.id} className="flex items-center justify-between gap-3 px-4 py-3 group">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                        <User className="w-4 h-4 text-gray-500" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <p className="text-sm font-medium text-gray-900 truncate">{name}</p>
                          {contact.is_primary && (
                            <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500 flex-shrink-0" />
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-x-3 text-xs text-gray-500">
                          {contact.role && <span>{contact.role}</span>}
                          {contact.email && contact.email !== selectedCustomer.email && (
                            <span className="flex items-center gap-1">
                              <Mail className="w-3 h-3" />
                              {contact.email}
                            </span>
                          )}
                          {contact.phone && contact.phone !== selectedCustomer.phone && (
                            <span className="flex items-center gap-1">
                              <Phone className="w-3 h-3" />
                              {formatUSPhone(contact.phone)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                      <button
                        onClick={() => openEditContactModal(contact)}
                        className="rounded p-1.5 text-blueNoir-800 transition-colors hover:bg-amber-50 hover:text-amber-700"
                        title="Edit"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleDeleteContactClick(contact)}
                        className="rounded p-1.5 text-blueNoir-800 transition-colors hover:bg-red-50 hover:text-red-700"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )
        })()}
      </div>

      {/* Auto-Approval Threshold */}
      {selectedCustomer.auto_approval_threshold && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
              <DollarSign className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-xs text-amber-600 font-medium">Auto-Approve Threshold</p>
              <p className="text-amber-900 font-bold text-lg">
                ${parseFloat(selectedCustomer.auto_approval_threshold).toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </p>
            </div>
          </div>
          <p className="text-xs text-amber-600 mt-2">Published initial estimates at or below this amount may be approved automatically. Additional work still requires the customer.</p>
        </div>
      )}

      {/* Notes */}
      {selectedCustomer.notes && (
        <div>
          <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Notes</h3>
          <div className="bg-gray-50 rounded-xl p-4">
            <p className="text-gray-700 whitespace-pre-wrap">{selectedCustomer.notes}</p>
          </div>
        </div>
      )}

      <div>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500">Truck relationships</h3>
            {!isLoadingVehicles && (
              <p className="mt-1 text-sm text-gray-600">
                {vehicleCount} truck{vehicleCount === 1 ? '' : 's'} connected to this company
              </p>
            )}
          </div>
          <div className="flex items-center justify-end gap-2">
            {isLoadingVehicles && <span className="text-xs text-gray-400">Loading...</span>}
            <button
              onClick={openAddVehicleModal}
              className="flex min-h-11 items-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white transition-[background-color,transform] duration-150 hover:bg-amber-600 active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2"
            >
              <Plus className="h-4 w-4" />
              Add / Link
            </button>
          </div>
        </div>
        {customerVehicles && customerVehicles.length > 0 && (
          <div className="mb-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              {shouldShowVehicleSearch && (
                <div className="relative min-w-0 flex-1">
                  <label className="sr-only" htmlFor="customer-truck-search">Search connected trucks</label>
                  <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                  <input
                    id="customer-truck-search"
                    type="search"
                    autoComplete="off"
                    enterKeyHint="search"
                    value={vehicleRelationshipSearch}
                    onChange={(event) => setVehicleRelationshipSearch(event.target.value)}
                    placeholder="Search unit, VIN, plate, make, model, owner..."
                    className="min-h-11 w-full rounded-lg border border-gray-300 bg-white py-2.5 pl-10 pr-11 text-sm text-gray-900 outline-none transition placeholder:text-gray-500 focus:border-amber-500 focus:ring-2 focus:ring-amber-200 [&::-webkit-search-cancel-button]:hidden"
                  />
                  {vehicleRelationshipSearch && (
                    <button
                      type="button"
                      onClick={() => setVehicleRelationshipSearch('')}
                      aria-label="Clear truck search"
                      className="absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
              )}
              {ownedVehicles.length > 0 && authorityVehicles.length > 0 && (
                <div className="flex shrink-0 flex-wrap gap-2" role="group" aria-label="Quick filters for truck relationships">
                  {([
                    ['all', 'All', vehicleCount],
                    ['owned', 'Owned', ownedVehicles.length],
                    ['authority', 'Under authority', authorityVehicles.length],
                  ] as const).map(([value, label, count]) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setVehicleRelationshipFilter(value)}
                      aria-pressed={vehicleRelationshipFilter === value}
                      className={`min-h-11 rounded-full border px-3.5 py-2 text-sm font-semibold transition-[background-color,border-color,color,transform] duration-150 active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 ${
                        vehicleRelationshipFilter === value
                          ? 'border-slate-700 bg-slate-800 text-white'
                          : 'border-gray-300 bg-white text-gray-700 hover:border-gray-400 hover:bg-gray-100'
                      }`}
                    >
                      {label} <span className={vehicleRelationshipFilter === value ? 'text-white/75' : 'text-gray-500'}>{count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {(shouldShowVehicleSearch || (customerVehicles?.length ?? 0) > 1) && (
              <div className="mt-2 flex min-h-11 items-center justify-between gap-3">
                {shouldShowVehicleSearch && vehicleRelationshipSearch.trim() ? (
                  <p className="text-xs text-gray-600" role="status">
                    Showing {visibleVehicleCount} of {vehicleCount} trucks
                  </p>
                ) : (
                  <span />
                )}
                {(customerVehicles?.length ?? 0) > 1 && (
                  <ViewToggle
                    value={vehiclesViewMode}
                    onChange={setVehiclesViewMode}
                    variant="light"
                  />
                )}
              </div>
            )}
          </div>
        )}
        {customerVehicles && customerVehicles.length > 0 ? (
          visibleCustomerVehicleGroups.length === 0 ? (
            <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 px-5 py-8 text-center">
              <Search className="mx-auto h-7 w-7 text-gray-400" />
              <p className="mt-2 text-sm font-semibold text-gray-800">No connected trucks match</p>
              <p className="mt-1 text-sm text-gray-500">Clear the search or relationship filter to see every truck.</p>
              <button
                type="button"
                onClick={() => {
                  setVehicleRelationshipSearch('')
                  setVehicleRelationshipFilter('all')
                }}
                className="mt-4 min-h-11 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-gray-700 shadow-sm ring-1 ring-gray-200 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
              >
                Clear filters
              </button>
            </div>
          ) : vehiclesViewMode === 'list' ? (
            <div className="bg-gray-50 rounded-xl border border-gray-100 overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="bg-gray-100 text-gray-600 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Vehicle</th>
                    {showVehicleUnitColumn && <th className="px-3 py-2 text-left font-medium">Unit</th>}
                    {showVehicleVinColumn && <th className="px-3 py-2 text-left font-medium">VIN</th>}
                    {showVehiclePlateColumn && <th className="px-3 py-2 text-left font-medium">Plate</th>}
                    <th className="px-3 py-2 text-right font-medium">Financial status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {visibleCustomerVehicleGroups.map((group) => {
                    const GroupIcon = group.icon
                    const isAuthorityGroup = group.key === 'authority'
                    return (
                    <React.Fragment key={group.key}>
                      <tr className={isAuthorityGroup ? 'bg-sky-50' : 'bg-amber-50'}>
                        <td colSpan={vehicleTableColumnCount} className="px-3 py-3">
                          <div className="flex items-start gap-2.5">
                            <GroupIcon className={`mt-0.5 h-4 w-4 shrink-0 ${isAuthorityGroup ? 'text-sky-700' : 'text-amber-700'}`} />
                            <div>
                              <p className={`text-xs font-semibold ${isAuthorityGroup ? 'text-sky-950' : 'text-amber-950'}`}>{group.title}</p>
                              <p className={`mt-0.5 text-xs font-normal ${isAuthorityGroup ? 'text-sky-800' : 'text-amber-800'}`}>{group.description}</p>
                            </div>
                            <span className={`ml-auto text-xs font-semibold ${isAuthorityGroup ? 'text-sky-800' : 'text-amber-800'}`}>{group.visibleVehicles.length}</span>
                          </div>
                        </td>
                      </tr>
                      {group.visibleVehicles.map((vehicle) => (
                    <tr 
                      key={vehicle.id} 
                      onClick={() => setSelectedVehicleInPanel(vehicle)}
                      className="hover:bg-gray-100/50 cursor-pointer group"
                    >
                      <td className="px-3 py-2.5 text-gray-900 font-medium">
                        {vehicleDisplayLabel(vehicle)}
                        {vehicle.color && <span className="text-gray-500 font-normal"> · {vehicle.color}</span>}
                        <span className="mt-1 block text-xs font-normal text-gray-500">
                          {vehicleRelationshipNote(vehicle, group.key)}
                        </span>
                      </td>
                      {showVehicleUnitColumn && (
                        <td className="px-3 py-2.5">
                          {vehicle.unit_number ? (
                            <span className="text-xs font-medium text-slate-700 bg-slate-100 rounded px-1.5 py-0.5">
                              {vehicle.unit_number}
                            </span>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                      )}
                      {showVehicleVinColumn && (
                        <td className="px-3 py-2.5">
                          {vehicle.vin ? (
                            <span className="font-mono text-xs text-gray-700">{vehicle.vin}</span>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                      )}
                      {showVehiclePlateColumn && (
                        <td className="px-3 py-2.5">
                          {vehicle.license_plate ? (
                            <span className="text-xs font-medium text-amber-700 bg-amber-100 rounded px-1.5 py-0.5">
                              {vehicle.license_plate}
                            </span>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                      )}
                      <td className="px-3 py-2.5 text-right">
                        {numericBalance(vehicle.balance) !== 0 ? (
                          <span className={`text-xs font-semibold ${balanceLabelClass(vehicle.balance)}`}>
                            {balanceLabel(vehicle.balance)}
                          </span>
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                    </tr>
                      ))}
                    </React.Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {visibleCustomerVehicleGroups.map((group) => {
                const GroupIcon = group.icon
                const isAuthorityGroup = group.key === 'authority'
                return (
                <React.Fragment key={group.key}>
                  <div className={`mt-2 rounded-xl border p-4 first:mt-0 ${
                    isAuthorityGroup ? 'border-sky-200 bg-sky-50' : 'border-amber-200 bg-amber-50'
                  }`}>
                    <div className="flex items-start gap-3">
                      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${isAuthorityGroup ? 'bg-sky-100 text-sky-700' : 'bg-amber-100 text-amber-700'}`}>
                        <GroupIcon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <p className={`text-[11px] font-bold uppercase tracking-wider ${isAuthorityGroup ? 'text-sky-700' : 'text-amber-700'}`}>
                          {isAuthorityGroup ? 'Authority fleet' : 'Owned fleet'}
                        </p>
                        <h4 className={`mt-0.5 text-sm font-semibold ${isAuthorityGroup ? 'text-sky-950' : 'text-amber-950'}`}>{group.title}</h4>
                        <p className={`mt-0.5 text-xs ${isAuthorityGroup ? 'text-sky-800' : 'text-amber-800'}`}>{group.description}</p>
                      </div>
                      <span className={`ml-auto shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${isAuthorityGroup ? 'bg-sky-100 text-sky-800' : 'bg-amber-100 text-amber-800'}`}>
                        {group.visibleVehicles.length}
                      </span>
                    </div>
                  </div>
                  {group.visibleVehicles.map((vehicle) => {
                const displayLabel = vehicleDisplayLabel(vehicle)
                const unitSuffix = vehicle.unit_number ? ` · Unit ${vehicle.unit_number}` : ''
                const cardTitle = unitSuffix && displayLabel.endsWith(unitSuffix)
                  ? displayLabel.slice(0, -unitSuffix.length)
                  : displayLabel
                const vehicleBalance = numericBalance(vehicle.balance)
                return (
                  <div
                    key={vehicle.id}
                    className="group relative rounded-xl border border-gray-200 bg-white p-4 pr-24 transition-colors hover:border-gray-300 hover:bg-gray-50"
                  >
                    <div
                      onClick={() => setSelectedVehicleInPanel(vehicle)}
                      className="cursor-pointer"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-gray-900">
                            {cardTitle}
                          </p>
                          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                            {vehicle.color && <span>{vehicle.color}</span>}
                            <span>{typeof vehicle.mileage === 'number' ? `${vehicle.mileage.toLocaleString()} mi` : 'No mileage'}</span>
                          </div>
                          <span className={`mt-2 inline-flex rounded-full px-2 py-1 text-[11px] font-bold uppercase tracking-wide ${
                            isAuthorityGroup ? 'bg-sky-100 text-sky-800' : 'bg-amber-100 text-amber-800'
                          }`}>
                            {isAuthorityGroup ? 'Under authority' : 'Owned'}
                          </span>
                          <p className="mt-2 text-xs font-medium text-slate-700">
                            {vehicleRelationshipNote(vehicle, group.key)}
                          </p>
                        </div>
                        <div className="flex max-w-full shrink-0 flex-col items-end gap-1 text-right">
                          {vehicle.unit_number && (
                            <span className="text-xs font-medium text-slate-700 bg-slate-100 rounded px-2 py-0.5">
                              Unit {vehicle.unit_number}
                            </span>
                          )}
                          {vehicle.license_plate && (
                            <span className="text-xs font-medium text-amber-700 bg-amber-100 rounded px-2 py-0.5">
                              {vehicle.license_plate}
                            </span>
                          )}
                          {vehicle.vin && (
                            <span className="max-w-full break-all font-mono text-[11px] text-gray-500">
                              VIN {vehicle.vin}
                            </span>
                          )}
                        </div>
                      </div>
                      {vehicleBalance !== 0 && (
                        <div className="mt-3 border-t border-gray-200 pt-2">
                          <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${
                            vehicleBalance > 0
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}>
                            {balanceLabel(vehicle.balance)}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="absolute right-2 top-2 flex items-center gap-1 opacity-100 xl:opacity-0 xl:transition-opacity xl:group-hover:opacity-100 xl:group-focus-within:opacity-100">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          openEditVehicleModal(vehicle)
                        }}
                        aria-label={`Edit ${cardTitle}`}
                        className="flex h-11 w-11 items-center justify-center rounded-lg bg-white text-blueNoir-800 shadow-sm ring-1 ring-gray-200 transition-colors hover:bg-amber-50 hover:text-amber-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
                        title="Edit"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteVehicleClick(vehicle)
                        }}
                        aria-label={`Delete ${cardTitle}`}
                        className="flex h-11 w-11 items-center justify-center rounded-lg bg-white text-blueNoir-800 shadow-sm ring-1 ring-gray-200 transition-colors hover:bg-red-50 hover:text-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                )
                  })}
                </React.Fragment>
                )
              })}
            </div>
          )
        ) : (
          <div className="bg-gray-50 rounded-xl p-6 text-center border border-gray-100">
            <Truck className="w-8 h-8 text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-500 mb-3">No vehicles on file</p>
            <button
              onClick={openAddVehicleModal}
              className="px-4 py-2 text-sm font-medium text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-lg transition-colors inline-flex items-center gap-1.5"
            >
              <Plus className="w-4 h-4" />
              Add First Vehicle
            </button>
          </div>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Activity</h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-50 rounded-xl p-4 text-center">
            <p className="text-2xl font-bold text-gray-900">
              {isLoadingVehicles ? '—' : vehicleCount}
            </p>
            <p className="text-xs text-gray-500">Vehicles</p>
          </div>
          <button
            type="button"
            onClick={() => setDetailTab('history')}
            className="bg-gray-50 rounded-xl p-4 text-center transition-colors hover:bg-amber-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
          >
            <p className="text-sm font-semibold text-gray-900">Repair history</p>
            <p className="mt-1 text-xs text-amber-700">View lifetime activity</p>
          </button>
          </div>
        </div>
      </>
      )}
    </div>
  )
}
