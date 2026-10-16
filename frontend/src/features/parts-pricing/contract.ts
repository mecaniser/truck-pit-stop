import { z } from 'zod'

const money = z.string().regex(/^\d{1,8}\.\d{2}$/)
const quantity = z.string().regex(/^\d+(?:\.\d+)?$/)
const id = z.string().min(1)
const origin = z.enum(['matrix', 'fixed', 'catalog', 'ad_hoc', 'internal', 'legacy_unknown'])
export const safePriceSchema = z.object({
  origin_source: origin, current_source: z.enum([...origin.options, 'manual']), managed: z.boolean(),
  default_unit_price: money.nullable(), charged_unit_price: money.nullable(), line_total: money.nullable(),
  pricing_version: z.number().int().nonnegative().nullable(), can_override: z.boolean(),
  policy_source: z.enum(['customer', 'shop', 'internal', 'legacy']).optional(),
}).strict()
export type SafePrice = z.infer<typeof safePriceSchema>
export type PriceSource = SafePrice['current_source']
export type PricingContext = { kind: 'repair_order'; repair_order_id: string }
  | { kind: 'fleet_draft'; vehicle_id: string; bill_to_customer_id: string | null }
  | { kind: 'counter_sale'; sale_id: string | null; customer_id: string | null; expected_sale_version: number | null }
export type PartAddLine = {
  client_key: string; inventory_id: string; quantity: string; source_line_id?: string | null; source_service_id?: string | null;
  pricing_intent: 'default' | 'manual' | 'stock'; unit_price?: string; price_override_reason?: string;
}
export type CounterPlanLine = { sale_line_id?: string; inventory_id: string; quantity: string; pricing_intent: 'default' | 'manual' | 'stock' | 'list'; charged_unit_price?: string; price_override_reason?: string }
export type PricingPlan = { kind: 'parts_add'; lines: PartAddLine[] }
  | { kind: 'service_apply'; service_id: string; quantity: string; attachment_path?: 'shop_flat_service' | 'fleet_legacy_service' }
  | { kind: 'pm_replace'; service_ids: string[] }
  | { kind: 'fleet_create'; service_ids: string[]; part_lines: PartAddLine[]; labor_lines?: { description: string; hours: string }[] }
  | { kind: 'counter_draft'; lines: CounterPlanLine[] }
export type ResolveRequest = { context: PricingContext; plan: PricingPlan; pricing_presentation?: 'shop' | 'fleet'; include_management_details?: boolean }
export const bandSchema = z.object({ min_cost: money, max_cost: money.nullable(), markup_percent: z.string().regex(/^\d+(?:\.\d{1,2})?$/) }).strict()
export type PricingBand = z.infer<typeof bandSchema>
const managementLine = z.object({
  line_key: id, snapshot_id: id.nullable(), actual_unit_cost: money.nullable(), actual_cost_known: z.boolean(),
  pricing_cost_floor: money.nullable(), pricing_basis: money.nullable(), minimum_sale_price: money.nullable(), effective_minimum: money.nullable(),
  fixed_catalog_price: z.boolean(), catalog_unit_price: money.nullable(),
  matrix: z.object({ id, revision_id: id, revision: z.number().int().positive(), name: z.string(), band: bandSchema }).strict().nullable(),
  override: z.object({ reason: z.string(), actor_id: id, occurred_at: z.string().datetime({ offset: true }) }).strict().nullable(),
}).strict()
export const managementSchema = z.object({ default_generation: z.number().int().nonnegative().nullable(), lines: z.array(managementLine).max(100) }).strict()
export type ManagementDetails = z.infer<typeof managementSchema>
const lineIdentity = {
  line_key: id, inventory_id: id, parts_usage_id: id.nullable(), sale_line_id: id.nullable(), source_service_id: id.nullable(), source_line_id: id.nullable(), source_component_id: id.nullable(),
  disposition: z.enum(['added', 'retained', 'removed', 'omitted']), name: z.string(), unit_type: z.string(), quantity,
  availability: z.object({ state: z.enum(['available', 'shortage', 'not_stocked', 'unknown']), requested_packages: z.number().nonnegative().nullable(), available_packages: z.number().nonnegative().nullable(), reserved_packages: z.number().nonnegative().nullable(), included: z.boolean() }).strict(),
}
const previewBase = {
  schema_version: z.literal(1), plan_kind: z.enum(['parts_add', 'service_apply', 'pm_replace', 'fleet_create', 'counter_draft']),
  pricing_preview_fingerprint: z.string().min(1), confirmation_required: z.boolean(), currency: z.literal('USD'), expected_sale_version: z.number().int().nonnegative().nullable(),
  availability: z.object({ state: z.enum(['ready', 'requires_stock_acknowledgement', 'partial_bundle']), omitted_line_keys: z.array(z.string()) }).strict(),
  warnings: z.array(z.object({ code: z.string(), message: z.string(), line_key: z.string().nullable(), inventory_id: z.string().nullable() }).strict()),
}
const shopTotals = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('repair_order'), parts_subtotal: money, labor_subtotal: money, labor_discount_amount: money, order_discount_amount: money, repair_total: money }).strict(),
  z.object({ kind: z.literal('counter_sale'), list_subtotal: money, charged_subtotal: money, discount_total: money, tax_total: money, total: money }).strict(),
])
export const previewSchema = z.discriminatedUnion('projection', [
  z.object({ ...previewBase, projection: z.literal('shop'), lines: z.array(z.object({ ...lineIdentity, pricing: safePriceSchema }).strict()).max(100), totals: shopTotals, management: managementSchema.nullable(), parts_pricing_fingerprint: z.string().nullable() }).strict(),
  z.object({ ...previewBase, projection: z.literal('fleet'), lines: z.array(z.object({ ...lineIdentity, pricing_version: z.number().int().nonnegative().nullable() }).strict()).max(100), totals: z.object({ kind: z.literal('repair_order'), repair_total: money }).strict() }).strict(),
])
export type PricingPreview = z.infer<typeof previewSchema>
export function parsePricingPreview(input: unknown, request: ResolveRequest, role?: string, conflict = false): PricingPreview {
  const preview = previewSchema.parse(input)
  const fleet = role === 'fleet_manager' || request.pricing_presentation === 'fleet'
  if (preview.projection !== (fleet ? 'fleet' : 'shop') || preview.plan_kind !== request.plan.kind) throw new Error('Invalid pricing preview')
  if ((request.context.kind === 'counter_sale') !== (preview.totals.kind === 'counter_sale')) throw new Error('Invalid pricing context')
  if (preview.projection === 'shop' && preview.management !== null && (conflict || !request.include_management_details || !['garage_owner', 'garage_admin'].includes(role ?? ''))) throw new Error('Unexpected private pricing details')
  if (new Set(preview.lines.map(line => line.line_key)).size !== preview.lines.length) throw new Error('Duplicate pricing identities')
  if (request.plan.kind === 'parts_add' && request.plan.lines.some(line => !preview.lines.some(quoted => quoted.line_key === line.client_key && quoted.inventory_id === line.inventory_id))) throw new Error('Mismatched quoted part')
  if (request.plan.kind === 'counter_draft' && request.plan.lines.some(line => !preview.lines.some(quoted => quoted.inventory_id === line.inventory_id && (!line.sale_line_id || quoted.sale_line_id === line.sale_line_id) && quoted.disposition !== 'removed'))) throw new Error('Mismatched quoted sale line')
  return preview
}
export function pricingError(error: unknown, fallback = 'Pricing could not be confirmed. Your draft is kept.'): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) { const messages = detail.flatMap(item => typeof item?.msg === 'string' ? [item.msg] : []); if (messages.length) return messages.slice(0, 4).join(' ') }
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message
  return fallback
}
export const priceSourceLabel = (source: PriceSource | null | undefined, policySource?: SafePrice['policy_source']) => source === 'matrix' && policySource === 'customer' ? 'Account matrix' : ({ matrix: 'Shop matrix', fixed: 'Fixed', catalog: 'Catalog', manual: 'Manual', ad_hoc: 'Manual', internal: 'At cost', legacy_unknown: 'Saved price' })[source ?? 'legacy_unknown']
export const pricingMoney = (value: string | null | undefined) => value == null ? '—' : new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' }).format(Number(value))
export const previewTotal = (preview: PricingPreview) => preview.totals.kind === 'counter_sale' ? preview.totals.total : preview.totals.repair_total

export class PricingCancelled extends Error { constructor() { super('Pricing review cancelled'); this.name = 'PricingCancelled' } }
