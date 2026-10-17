import { z } from 'zod'
import { bandSchema } from './contract'
const money = z.string().regex(/^\d{1,8}\.\d{2}$/)
const matrixSummary = z.object({ id: z.string(), name: z.string(), version: z.number().int().positive(), current_revision: z.number().int().positive(), current_revision_id: z.string(), is_default: z.boolean(), archived_at: z.string().nullable(), created_at: z.string(), updated_at: z.string() }).strict()
export const matrixListSchema = z.object({ schema_version: z.literal(1), items: z.array(matrixSummary), next_cursor: z.string().nullable() }).strict()
export const matrixDetailSchema = z.object({ schema_version: z.literal(1), matrix: matrixSummary.extend({ bands: z.array(bandSchema) }).strict() }).strict()
export const defaultSchema = z.object({ matrix_id: z.string().nullable(), generation: z.number().int().nonnegative() }).strict()
export const historySchema = z.object({ schema_version: z.literal(1), items: z.array(z.object({ id: z.string(), matrix_id: z.string(), revision: z.number().int(), name: z.string(), bands: z.array(bandSchema), created_at: z.string(), created_by_user_id: z.string().nullable() }).strict()), next_cursor: z.string().nullable() }).strict()
export const policySchema = z.object({ schema_version: z.literal(1), policy: z.object({ inventory_id: z.string(), pricing_version: z.number().int().nonnegative(), actual_unit_cost: money.nullable(), actual_cost_known: z.boolean(), selling_price: money, pricing_cost_floor: money.nullable(), minimum_sale_price: money.nullable(), fixed_sales_price: z.boolean() }).strict() }).strict()
const evaluation = z.object({ status: z.enum(['priced', 'blocked']), unit_price: money.nullable(), source: z.enum(['matrix', 'fixed', 'catalog']).nullable(), pricing_basis: money.nullable(), effective_minimum: money.nullable(), band: bandSchema.nullable(), gross_profit: z.string().nullable(), markup_percent: z.string().nullable(), margin_percent: z.string().nullable(), warnings: z.array(z.object({ code: z.string(), message: z.string() }).strict()), errors: z.array(z.object({ code: z.string(), message: z.string() }).strict()) }).strict()
export const sampleSchema = z.object({ schema_version: z.literal(1), currency: z.literal('USD'), current_default: defaultSchema, cases: z.array(z.object({ sample_key: z.string(), inventory_id: z.string().nullable(), label: z.string(), actual_unit_cost: money.nullable(), actual_cost_known: z.boolean(), catalog_unit_price: money.nullable(), current: evaluation, proposed: evaluation }).strict()) }).strict()
export type MatrixDetail = z.infer<typeof matrixDetailSchema>['matrix']
export type InventoryPricingPolicy = z.infer<typeof policySchema>['policy']
/** Formatting an entered decimal is not pricing calculation. Reject exponent,
 * negative and overprecision inputs before they enter a command. */
export function enteredMoney(input: string): string | null {
  const value = input.trim()
  if (!value) return null
  if (!/^\d{1,8}(?:\.\d{1,2})?$/.test(value)) throw new Error('Enter an amount with up to two decimals.')
  const [whole, decimals = ''] = value.split('.')
  return `${whole.replace(/^0+(?=\d)/, '')}.${decimals.padEnd(2, '0')}`
}
