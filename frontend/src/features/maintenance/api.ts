import { ZodError } from 'zod'
import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { isPricingScopeCurrent, usePricingScope } from '@/features/parts-pricing/usePricingScope'
import { pricingError } from '@/features/parts-pricing/contract'
import { orderMaintenanceSchema, programPageSchema, type Channel, type Program } from './contract'

export const maintenancePath = (vehicleId: string) => `/vehicles/${vehicleId}/maintenance-programs`
export const programPath = (vehicleId: string, programId: string) => `${maintenancePath(vehicleId)}/${programId}`
export function scopedProgram(program: Program, vehicleId: string, programId?: string) {
  if (program.vehicle_id !== vehicleId || (programId && program.id !== programId)) throw new Error('Maintenance response does not match this truck.')
  return program
}
export function usePrograms(vehicleId: string, channel: Channel, archived = false, page = 0) {
  const scope = usePricingScope()
  return useQuery({ queryKey: ['maintenance', scope, vehicleId, channel, archived, page], gcTime: 0, retry: false, refetchOnWindowFocus: false,
    queryFn: async ({ signal }) => { const result = programPageSchema.parse((await api.get(maintenancePath(vehicleId), { signal, params: { channel, include_archived: archived, skip: page * 25, limit: 25 } })).data); result.items.forEach(program => scopedProgram(program, vehicleId)); return result },
  })
}
export function useOrderMaintenance(orderId: string, enabled: boolean) {
  const scope = usePricingScope()
  return useQuery({ queryKey: ['maintenance-order', scope, orderId], enabled: enabled && Boolean(orderId), gcTime: 0, retry: false, refetchOnWindowFocus: false,
    queryFn: async ({ signal }) => { const result = orderMaintenanceSchema.parse((await api.get(`/repair-orders/${orderId}/maintenance`, { signal })).data); if (result.repair_order_id !== orderId) throw new Error('Maintenance response does not match this order.'); return result },
  })
}
export class MaintenanceCancelled extends Error { constructor() { super('Maintenance context changed.'); this.name = 'MaintenanceCancelled' } }
export const errorDetail = (failure: unknown) => (failure as { response?: { status?: number; data?: { detail?: { code?: string; message?: string; preview?: unknown; current_version?: number } } } })?.response?.data?.detail
export const maintenanceError = (failure: unknown) => failure instanceof ZodError ? 'Maintenance data could not be verified. Reload and try again.' : pricingError(failure, failure instanceof Error ? failure.message : 'Maintenance could not be saved. Your draft is kept.')
export function invalidateMaintenance(client: QueryClient) { for (const prefix of ['maintenance', 'maintenance-order', 'maintenance-history']) void client.invalidateQueries({ queryKey: [prefix] }) }
/** Mutation identities survive an uncertain response; inputs and preview responses stay scoped. */
export function useMaintenanceCommand(context: string) {
  const scope = usePricingScope(); const client = useQueryClient()
  const live = useRef(`${scope}:${context}`); live.current = `${scope}:${context}`
  const controller = useRef(new AbortController())
  const attempt = useRef<{ semantic: string; id: string } | null>(null)
  const locked = useRef(false); const [busy, setBusy] = useState(false)
  useEffect(() => { const active = new AbortController(); controller.current = active; attempt.current = null; return () => active.abort() }, [scope, context])
  const run = async <T,>(path: string, body: unknown, parse: (value: unknown) => T, method: 'post' | 'patch' = 'post', preview = false): Promise<T> => {
    if (locked.current) throw new Error('A maintenance request is already pending.')
    locked.current = true; setBusy(true)
    const identity = `${scope}:${context}`; const signal = controller.current.signal
    const current = () => !signal.aborted && live.current === identity && isPricingScopeCurrent(scope)
    const semantic = JSON.stringify([path, method, body], (key, value) => key.startsWith('expected_') && key.endsWith('_fingerprint') ? undefined : value)
    if (!preview && attempt.current?.semantic !== semantic) attempt.current = { semantic, id: crypto.randomUUID() }
    try {
      if (!current()) throw new MaintenanceCancelled()
      const result = await api[method](path, body, { signal, skipAuthRefresh: true, ...(!preview ? { headers: { 'Idempotency-Key': attempt.current!.id } } : {}) })
      if (!current()) throw new MaintenanceCancelled()
      const value = parse(result.data)
      if (!preview) { attempt.current = null; for (const prefix of ['maintenance', 'maintenance-order', 'maintenance-history', 'fleet-board', 'fleet-truck', 'fleet-truck-history', 'repair-orders', 'price-build', 'fleet-price-build', 'fleet-ro-detail', 'repair-order-workspace', 'repair-order-detail', 'customerVehicleRepairOrders', 'maintenance-drafts', 'maintenance-operations']) void client.invalidateQueries({ queryKey: [prefix] }) }
      return value
    } catch (failure) { if (!current()) throw new MaintenanceCancelled(); if (['maintenance_version_conflict', 'maintenance_cycle_claimed', 'maintenance_operation_linked', 'maintenance_review_required', 'maintenance_restore_conflict'].includes(errorDetail(failure)?.code ?? '')) invalidateMaintenance(client); throw failure }
    finally { locked.current = false; if (current()) setBusy(false) }
  }
  return { run, busy }
}
