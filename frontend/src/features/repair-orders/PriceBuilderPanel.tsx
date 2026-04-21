import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Pencil, RefreshCcw, Search, Trash2 } from 'lucide-react'

import api from '@/lib/api'
import BaseSelect from '@/components/BaseSelect'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import { PartsUsage, PriceBuildSummary, RepairOperationCandidate, RepairOrderStatus, Service } from '@/types'

type Props = {
  orderId: string
  orderStatus: RepairOrderStatus
  services?: Service[]
  canEdit: boolean
  defaultLaborRate?: number
  description?: string | null
  onUpdated?: () => void
}

type SearchResponse = {
  candidates: RepairOperationCandidate[]
  warnings: { code: string; message: string }[]
}

export default function PriceBuilderPanel({
  orderId,
  orderStatus,
  services,
  canEdit,
  defaultLaborRate,
  description,
  onUpdated,
}: Props) {
  const queryClient = useQueryClient()
  const [serviceId, setServiceId] = useState('')
  const [serviceHours, setServiceHours] = useState(1)
  const [searchTerm, setSearchTerm] = useState('')
  const [candidates, setCandidates] = useState<RepairOperationCandidate[]>([])
  const [searchWarnings, setSearchWarnings] = useState<{ code: string; message: string }[]>([])
  // Local edits per line: tracks hours/rate as user types for live total preview
  const [lineEdits, setLineEdits] = useState<Record<string, { hours: string; rate: string }>>({})
  const getLineHours = (id: string, fallback: string) => lineEdits[id]?.hours ?? fallback
  const getLineRate  = (id: string, fallback: string) => lineEdits[id]?.rate  ?? fallback
  const getLineTotal = (id: string, _fallback: string, serverTotal: string) => {
    if (!lineEdits[id]) return serverTotal
    const h = parseFloat(lineEdits[id].hours) || 0
    const r = parseFloat(lineEdits[id].rate)  || 0
    return (h * r).toFixed(2)
  }
  const clearLineEdit = (id: string) =>
    setLineEdits((prev) => { const next = { ...prev }; delete next[id]; return next })

  const { data: summary, refetch, isLoading } = useQuery<PriceBuildSummary>({
    queryKey: ['price-build', orderId],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${orderId}/price-build`)
      return response.data
    },
    enabled: !!orderId,
  })

  const { data: partsUsed, refetch: refetchParts } = useQuery<PartsUsage[]>({
    queryKey: ['price-build-parts', orderId],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${orderId}/parts`)
      return response.data
    },
    enabled: !!orderId,
  })

  const [editingPartsId, setEditingPartsId] = useState<string | null>(null)
  const [editingPartsQty, setEditingPartsQty] = useState<string>('')
  const [editingPartsSaving, setEditingPartsSaving] = useState(false)

  const isLocked = !!summary?.pricing_locked
  const canMutate = canEdit && !isLocked && ['draft', 'quoted'].includes(orderStatus)

  const serviceOptions = useMemo(() => {
    const list = services || []
    return list
      .filter((svc) => svc.is_active !== false)
      .map((svc) => ({
        value: svc.id,
        label: svc.name,
      }))
  }, [services])

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['price-build', orderId] })
    await queryClient.invalidateQueries({ queryKey: ['price-build-parts', orderId] })
    await queryClient.invalidateQueries({ queryKey: ['repair-order-detail', orderId] })
    await queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
    await refetch()
    await refetchParts()
    onUpdated?.()
  }

  const addServiceLaborLine = useMutation({
    mutationFn: async () => {
      await api.post(`/repair-orders/${orderId}/price-build/flat-service`, {
        service_id: serviceId,
        quantity: serviceHours,
      })
    },
    onSuccess: async () => {
      setServiceId('')
      setServiceHours(1)
      await invalidate()
      toast.success('Labor line added')
    },
    onError: () => toast.error('Unable to add labor line'),
  })

  const searchOps = useMutation({
    mutationFn: async (): Promise<SearchResponse> => {
      const response = await api.post(`/repair-orders/${orderId}/price-build/repair-ops/search`, {
        query: searchTerm,
      })
      return response.data
    },
    onSuccess: (data) => {
      setCandidates(data.candidates || [])
      setSearchWarnings(data.warnings || [])
    },
    onError: () => toast.error('Repair operation search failed'),
  })

  const applyRepairOp = useMutation({
    mutationFn: async (candidate: RepairOperationCandidate) => {
      await api.post(`/repair-orders/${orderId}/price-build/repair-ops/apply`, {
        operation_id: candidate.operation_id,
        name: candidate.name,
        description: candidate.description,
        estimated_hours: candidate.estimated_hours,
        provider: candidate.provider,
        auto_recalc_enabled: true,
      })
    },
    onSuccess: async () => {
      await invalidate()
      toast.success('Repair operation applied')
    },
    onError: () => toast.error('Unable to apply operation'),
  })

  const updateLine = useMutation({
    mutationFn: async ({
      lineId,
      body,
    }: {
      lineId: string
      body: { description?: string; hours?: number; hourly_rate?: number }
    }) => {
      await api.patch(`/repair-orders/${orderId}/price-build/lines/${lineId}`, body)
    },
    onSuccess: async () => {
      await invalidate()
    },
    onError: () => toast.error('Unable to update line'),
  })

  const removeLine = useMutation({
    mutationFn: async (lineId: string) => {
      await api.delete(`/repair-orders/${orderId}/price-build/lines/${lineId}`)
    },
    onSuccess: async () => {
      await invalidate()
      toast.success('Line removed')
    },
    onError: () => toast.error('Unable to remove line'),
  })

  const recalc = useMutation({
    mutationFn: async () => {
      await api.post(`/repair-orders/${orderId}/price-build/recalculate`)
    },
    onSuccess: async () => {
      await invalidate()
      toast.success('Price recalculated')
    },
    onError: () => toast.error('Recalculation failed'),
  })

  const lineTypeLabel = (line: { line_type: string; source_service_id?: string | null }) => {
    if (line.source_service_id) return 'service labor'
    return line.line_type.replace('_', ' ')
  }

  useEffect(() => {
    if (!defaultLaborRate || !canMutate) return
    // No-op placeholder: keeps default labor rate available for future quick-add UX.
  }, [defaultLaborRate, canMutate])

  return (
    <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5">
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">Price Builder</h3>
          <SectionInfoTooltip
            text="Builds the billable price for this repair order. Add diagnostic hours, repair operations, or sublet work. Lock pricing once you're ready to quote the customer — no changes allowed after that."
            tooltipClassName="w-72"
          />
        </span>
        <button
          type="button"
          onClick={() => recalc.mutate()}
          disabled={!canMutate || recalc.isPending}
          className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-2.5 py-1.5 text-xs font-medium text-gray-700 disabled:opacity-50"
        >
          <RefreshCcw className="h-3.5 w-3.5" />
          Recalculate
        </button>
      </div>

      {description && description.trim() && (
        <div>
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-1">Work Requested</p>
          <div className="rounded-lg bg-gray-50 p-3 text-sm text-gray-800 whitespace-pre-wrap">
            {description}
          </div>
        </div>
      )}

      {isLocked && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Pricing locked{summary?.pricing_lock_reason ? ` (${summary.pricing_lock_reason})` : ''}. Edit is disabled.
        </div>
      )}

      {!!summary?.warnings?.length && (
        <div className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          {summary.warnings.map((w) => (
            <p key={`${w.code}-${w.message}`} className="text-xs text-amber-800">
              {w.message}
            </p>
          ))}
        </div>
      )}

      {!!searchWarnings.length && (
        <div className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          {searchWarnings.map((w) => (
            <p key={`${w.code}-${w.message}`} className="text-xs text-amber-800">
              {w.message}
            </p>
          ))}
        </div>
      )}

      <div className="space-y-2">
        <span className="inline-flex items-center gap-1">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Diagnostics / Inspection (Hourly)</p>
          <SectionInfoTooltip text="Select a diagnostic or inspection service and enter the number of hours. Billed at your shop's standard hourly rate — not a flat fee. Use this for initial check-ups, not specific repairs." />
        </span>
        <div className="flex items-center gap-2">
          <div className="flex-1 min-w-0">
            <BaseSelect
              options={serviceOptions}
              value={serviceId}
              onChange={setServiceId}
              placeholder="Select diagnostics or inspection service"
              allowAddNew={false}
            />
          </div>
          <input
            type="number"
            min={1}
            value={serviceHours}
            onChange={(e) => setServiceHours(Math.max(1, parseInt(e.target.value, 10) || 1))}
            className="h-[42px] w-14 shrink-0 rounded-lg border border-gray-300 px-2 text-sm"
            aria-label="Hours"
          />
          <button
            type="button"
            onClick={() => addServiceLaborLine.mutate()}
            disabled={!canMutate || !serviceId || addServiceLaborLine.isPending}
            className="h-[42px] shrink-0 rounded-lg bg-amber-500 px-3 text-sm font-medium text-white disabled:bg-gray-300"
          >
            Add
          </button>
        </div>
        <p className="text-[11px] text-gray-500">This adds labor hours at your shop hourly rate (no flat fee pricing).</p>
      </div>

      <div className="space-y-2">
        <span className="inline-flex items-center gap-1">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Repair Operation</p>
          <SectionInfoTooltip text="Search your repair operation library for standard jobs (e.g. brake pad replacement, EGR cleaning, tire rotation). Estimated hours come from historical data and auto-recalculate as rates change. Adjust hours or rate manually at any time." tooltipClassName="w-72" />
        </span>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search repair operation (e.g. brake change, EGR)"
            className="h-[42px] flex-1 rounded-lg border border-gray-300 px-3 text-sm"
          />
          <button
            type="button"
            onClick={() => searchOps.mutate()}
            disabled={!searchTerm.trim() || searchOps.isPending}
            className="inline-flex h-[42px] items-center gap-1 rounded-lg border border-gray-300 px-3 text-sm font-medium text-gray-700 disabled:opacity-50"
          >
            <Search className="h-4 w-4" />
            Search
          </button>
        </div>
        {!!candidates.length && (
          <div className="space-y-2 rounded-lg border border-gray-200 p-2">
            {candidates.map((c) => (
              <div key={c.operation_id} className="flex items-center justify-between rounded-md border border-gray-100 px-2 py-2">
                <div>
                  <p className="text-sm font-medium text-gray-800">{c.name}</p>
                  <p className="text-xs text-gray-500">{c.description || c.operation_id}</p>
                  <p className="text-xs text-gray-600">{parseFloat(c.estimated_hours || '0').toFixed(2)}h</p>
                </div>
                <button
                  type="button"
                  onClick={() => applyRepairOp.mutate(c)}
                  disabled={!canMutate || applyRepairOp.isPending}
                  className="rounded-lg bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-white disabled:bg-gray-300"
                >
                  Apply
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {(() => {
        const allParts = partsUsed || []
        const lines = summary?.lines || []
        const partsByService = new Map<string, typeof allParts>()
        const orphanParts: typeof allParts = []
        for (const pu of allParts) {
          if (pu.source_service_id) {
            const bucket = partsByService.get(pu.source_service_id) || []
            bucket.push(pu)
            partsByService.set(pu.source_service_id, bucket)
          } else {
            orphanParts.push(pu)
          }
        }

        const renderPartsRows = (parts: typeof allParts) => (
          <div className="overflow-x-auto rounded-md border border-gray-200 bg-gray-50/50">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] text-gray-500 border-b border-gray-200">
                  <th className="py-1.5 px-2.5 font-medium">Part</th>
                  <th className="py-1.5 px-2.5 font-medium text-right">Qty</th>
                  <th className="py-1.5 px-2.5 font-medium text-right">Unit</th>
                  <th className="py-1.5 px-2.5 font-medium text-right">Line total</th>
                </tr>
              </thead>
              <tbody>
                {parts.map((pu) => {
                  const isEditing = editingPartsId === pu.id
                  return (
                    <tr key={pu.id} className="border-b border-gray-100 last:border-0">
                      <td className="py-1.5 px-2.5 text-gray-800">
                        <div className="font-medium">{pu.inventory_name}</div>
                        <div className="text-xs text-gray-500">{pu.inventory_sku}</div>
                      </td>
                      <td className="py-1.5 px-2.5 text-right text-gray-800">
                        {isEditing ? (
                          <div className="inline-flex items-center gap-1">
                            <input
                              type="number"
                              min={1}
                              value={editingPartsQty}
                              onChange={(e) => setEditingPartsQty(e.target.value)}
                              className="w-16 h-7 px-2 text-right rounded border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                              autoFocus
                            />
                            <button
                              type="button"
                              disabled={editingPartsSaving}
                              onClick={async () => {
                                const num = Number(editingPartsQty)
                                if (!Number.isFinite(num) || num < 1) {
                                  toast.error('Quantity must be at least 1')
                                  return
                                }
                                if (num === pu.quantity) {
                                  setEditingPartsId(null)
                                  return
                                }
                                setEditingPartsSaving(true)
                                try {
                                  await api.patch(`/repair-orders/${orderId}/parts/${pu.id}`, { quantity: num })
                                  await invalidate()
                                  toast.success(`${pu.inventory_name} qty updated to ${num}`)
                                  setEditingPartsId(null)
                                } catch (err: any) {
                                  const detail = err?.response?.data?.detail
                                  toast.error(typeof detail === 'string' && detail ? detail : 'Failed to update quantity')
                                } finally {
                                  setEditingPartsSaving(false)
                                }
                              }}
                              className="h-7 px-2 text-xs font-semibold text-white bg-amber-600 rounded hover:bg-amber-700 disabled:opacity-60"
                            >
                              {editingPartsSaving ? '…' : 'Save'}
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingPartsId(null)}
                              className="h-7 px-1.5 text-xs text-gray-600 hover:text-gray-900"
                            >
                              ✕
                            </button>
                          </div>
                        ) : (
                          <span className="inline-flex items-center gap-1.5">
                            {pu.quantity}
                            {canMutate && (
                              <button
                                type="button"
                                onClick={() => {
                                  setEditingPartsId(pu.id)
                                  setEditingPartsQty(String(pu.quantity))
                                }}
                                className="text-amber-700 hover:text-amber-800"
                                aria-label={`Edit quantity for ${pu.inventory_name}`}
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            )}
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 px-2.5 text-right text-gray-600">${parseFloat(pu.unit_price).toFixed(2)}</td>
                      <td className="py-1.5 px-2.5 text-right text-gray-900 font-medium">${parseFloat(pu.total_price).toFixed(2)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )

        const renderLaborEditor = (line: typeof lines[number]) => (
          <>
            <input
              defaultValue={line.description}
              onBlur={(e) => {
                const value = e.target.value.trim()
                if (value !== line.description) {
                  updateLine.mutate({ lineId: line.id, body: { description: value } })
                }
              }}
              disabled={!canMutate}
              className="mb-2 w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm disabled:bg-gray-100"
            />
            <div className="flex items-end gap-1.5">
              <div className="flex flex-col gap-0.5 flex-1">
                <span className="text-[10px] text-gray-400">Hours</span>
                <input
                  type="number"
                  step="0.25"
                  min="0"
                  value={getLineHours(line.id, line.hours)}
                  onChange={(e) =>
                    setLineEdits((prev) => ({
                      ...prev,
                      [line.id]: { hours: e.target.value, rate: getLineRate(line.id, line.hourly_rate) },
                    }))
                  }
                  onBlur={(e) => {
                    const value = parseFloat(e.target.value || '0')
                    if (!Number.isNaN(value) && value.toString() !== line.hours) {
                      updateLine.mutate({ lineId: line.id, body: { hours: value } })
                    }
                    clearLineEdit(line.id)
                  }}
                  disabled={!canMutate}
                  className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm disabled:bg-gray-100"
                />
              </div>
              <div className="flex flex-col gap-0.5 flex-1">
                <span className="text-[10px] text-gray-400">Rate/hr</span>
                <input
                  type="text"
                  inputMode="decimal"
                  value={lineEdits[line.id]?.rate ?? parseFloat(line.hourly_rate).toFixed(2)}
                  onChange={(e) =>
                    setLineEdits((prev) => ({
                      ...prev,
                      [line.id]: { hours: getLineHours(line.id, line.hours), rate: e.target.value },
                    }))
                  }
                  onBlur={(e) => {
                    const value = parseFloat(e.target.value || '0')
                    if (!Number.isNaN(value) && value.toString() !== line.hourly_rate) {
                      updateLine.mutate({ lineId: line.id, body: { hourly_rate: value } })
                    }
                    clearLineEdit(line.id)
                  }}
                  disabled={!canMutate}
                  className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm disabled:bg-gray-100"
                />
              </div>
              <div className="flex flex-col gap-0.5 flex-1">
                <span className="text-[10px] text-gray-400">Total</span>
                <div className="rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-sm font-semibold text-gray-800">
                  ${getLineTotal(line.id, line.hours, line.total_cost || '0')}
                </div>
              </div>
              <button
                type="button"
                onClick={() => removeLine.mutate(line.id)}
                disabled={!canMutate || removeLine.isPending}
                className="inline-flex items-center justify-center rounded-md border border-red-200 p-1.5 text-red-600 disabled:opacity-50 shrink-0"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </>
        )

        if (isLoading) {
          return <p className="text-sm text-gray-500">Loading…</p>
        }
        if (!lines.length && !orphanParts.length) {
          return <p className="text-sm text-gray-500">No price-build lines yet.</p>
        }

        return (
          <div className="space-y-2">
            <span className="inline-flex items-center gap-1">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Services & Labor</p>
              <SectionInfoTooltip text="Each card is one billable item. Service packages bundle labor with their required parts — edit hours, rate, or part quantity inline. Stock adjusts automatically." tooltipClassName="w-72" />
            </span>
            <div className="space-y-3">
              {lines.map((line) => {
                const groupedParts = line.source_service_id ? partsByService.get(line.source_service_id) || [] : []
                return (
                  <div key={line.id} className="rounded-lg border border-gray-200 p-3 space-y-2">
                    <div className="text-[11px] uppercase tracking-wide text-gray-400">{lineTypeLabel(line)}</div>
                    {renderLaborEditor(line)}
                    {groupedParts.length > 0 && (
                      <div className="pt-1">
                        <p className="text-[11px] font-medium text-gray-500 mb-1">Parts included</p>
                        {renderPartsRows(groupedParts)}
                      </div>
                    )}
                  </div>
                )
              })}
              {orphanParts.length > 0 && (
                <div className="rounded-lg border border-gray-200 p-3 space-y-2">
                  <div className="text-[11px] uppercase tracking-wide text-gray-400">parts only</div>
                  {renderPartsRows(orphanParts)}
                </div>
              )}
            </div>
          </div>
        )
      })()}

      <div className="rounded-lg border-t border-gray-200 pt-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <span className="text-gray-500">Parts</span>
          <span className="font-semibold text-blue-700">${parseFloat(summary?.parts_total || '0').toFixed(2)}</span>
          <span className="text-gray-400">·</span>
          <span className="text-gray-500">Labor/Services</span>
          <span className="font-semibold text-amber-700">${parseFloat(summary?.labor_total || '0').toFixed(2)}</span>
          <span className="text-gray-400">·</span>
          <span className="text-gray-500">Total</span>
          <span className="text-base font-bold text-gray-900">${parseFloat(summary?.total_cost || '0').toFixed(2)}</span>
        </div>
      </div>
    </div>
  )
}
