import { z } from 'zod'
import { enteredMoney } from '@/features/parts-pricing/configuration'

const money = z.string().regex(/^\d{1,8}\.\d{2}$/)
const source = z.enum(['customer', 'shop', 'internal'])
const matrix = z.object({ id: z.string(), revision_id: z.string(), revision: z.number().int().positive(), name: z.string() }).strict()
const values = z.object({ labor_rate: money.nullable(), parts_matrix_id: z.string().nullable() }).strict()
export const customerPolicySchema = z.object({
  schema_version: z.literal(1), customer_id: z.string(), version: z.number().int().nonnegative(), configured: values,
  effective: z.object({ labor: z.object({ source, rate: money.nullable() }).strict(), parts: z.object({ source, mode: z.enum(['matrix', 'catalog', 'internal']), matrix: matrix.nullable() }).strict() }).strict(),
  can_edit: z.boolean(), ineligible_reason: z.literal('internal_account').nullable(), updated_at: z.string().nullable(),
}).strict()
export const customerHistorySchema = z.object({ schema_version: z.literal(1), items: z.array(z.object({ id: z.string(), version: z.number().int().nonnegative(), before: values, after: values, actor_user_id: z.string().nullable(), actor_display_name: z.string().nullable(), reason: z.string(), occurred_at: z.string() }).strict()), next_cursor: z.string().nullable() }).strict()
const intakeBase = { schema_version: z.literal(1), customer_id: z.string(), vehicle_id: z.string().nullable(), expected_pricing_policy: z.string().min(1), policy_kind: z.enum(['external', 'internal']) }
export const intakeSchema = z.discriminatedUnion('projection', [
  z.object({ ...intakeBase, projection: z.literal('shop'), labor: z.object({ source, rate: money.nullable() }).strict(), parts: z.object({ source, mode: z.enum(['matrix', 'catalog', 'internal']) }).strict() }).strict(),
  z.object({ ...intakeBase, projection: z.literal('fleet'), agreement_applies: z.boolean() }).strict(),
])
export type CustomerPricingPolicy = z.infer<typeof customerPolicySchema>
export type IntakePricing = z.infer<typeof intakeSchema>
export type ShopOrderPolicy = { schema_version: 1; snapshot_id: string | null; mode: 'captured' | 'legacy' | 'internal'; labor: { source: 'customer' | 'shop' | 'legacy' | 'internal'; rate: string | null }; parts: { source: 'customer' | 'shop' | 'legacy' | 'internal'; mode: 'matrix' | 'catalog' | 'legacy' | 'internal' } }
export type SafeLaborPricing = { source: 'customer' | 'shop' | 'internal' | 'legacy_unknown'; current_source: 'default' | 'manual' | 'legacy_unknown'; default_hourly_rate: string | null; charged_hourly_rate: string; can_override: boolean }
export const policySourceLabel = (value: string) => ({ customer: 'Account', shop: 'Shop', internal: 'Internal', legacy: 'Saved', legacy_unknown: 'Saved' })[value] ?? 'Saved'
export const laborSourceLabel = (pricing: SafeLaborPricing) => pricing.current_source === 'manual' ? 'Manual' : policySourceLabel(pricing.source)
export function accountRate(input: string) {
  const value = enteredMoney(input)
  if (value !== null && /^0\.00$/.test(value)) throw new Error('Enter a rate greater than zero, or leave it blank for the shop rate.')
  return value
}
export function parseIntake(input: unknown, customerId: string, vehicleId: string | null, projection: 'shop' | 'fleet') {
  const result = intakeSchema.parse(input)
  if (result.customer_id !== customerId || result.vehicle_id !== vehicleId || result.projection !== projection) throw new Error('Invalid account pricing response')
  return result
}
