import { z } from 'zod'
import { stateSchema } from './contract'

const positionSchema = z.object({
  scope: z.string(), vehicleId: z.string().uuid(), issueId: z.string().uuid(),
  filter: z.union([stateSchema, z.literal('all')]), skip: z.number().int().nonnegative(),
})
const returnSchema = positionSchema.extend({
  pathname: z.enum(['/dashboard', '/dashboard/repair-orders', '/dashboard/customers']), search: z.string(),
  sourceOrderId: z.string().uuid().nullable(), customerId: z.string().uuid().nullable(), targetOrderId: z.string().uuid(),
})
export type TruckIssueReturn = z.infer<typeof returnSchema>
export function readTruckIssueReturn(value: unknown, scope: string, targetOrderId: string | null) {
  const parsed = returnSchema.safeParse((value as { truckIssueReturn?: unknown } | null)?.truckIssueReturn)
  if (!parsed.success || parsed.data.scope !== scope || parsed.data.targetOrderId !== targetOrderId || !parsed.data.search.startsWith('?')) return null
  const origin = parsed.data
  const params = new URLSearchParams(origin.search)
  if (origin.pathname === '/dashboard/customers') {
    return origin.customerId && params.get('selected') === origin.customerId && params.get('vehicle') === origin.vehicleId ? origin : null
  }
  if (!origin.sourceOrderId || params.get('selected') !== origin.sourceOrderId) return null
  if (origin.customerId) return params.get('customer') === origin.customerId && params.get('customer_vehicle') === origin.vehicleId ? origin : null
  return origin.sourceOrderId !== targetOrderId ? origin : null
}
export function readTruckIssueRestore(value: unknown, scope: string, vehicleId: string) {
  const parsed = positionSchema.safeParse((value as { truckIssueRestore?: unknown } | null)?.truckIssueRestore)
  return parsed.success && parsed.data.scope === scope && parsed.data.vehicleId === vehicleId ? parsed.data : null
}
