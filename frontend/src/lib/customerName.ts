/**
 * Customer display name. The business is LLC-based, so the company name is the
 * primary identifier; the personal name is a fallback for customers that have
 * no company set (legacy/individual records).
 */
export interface CustomerNameFields {
  first_name?: string | null
  last_name?: string | null
  company_name?: string | null
}

/**
 * Primary display name for a customer: company name when present, otherwise
 * "First Last". Returns `fallback` when nothing usable is available.
 */
export function customerDisplayName(
  customer?: CustomerNameFields | null,
  fallback = 'Unknown customer',
): string {
  if (!customer) return fallback
  const company = (customer.company_name || '').trim()
  if (company) return company
  const personal = `${customer.first_name || ''} ${customer.last_name || ''}`.trim()
  return personal || fallback
}

/** Secondary personal name ("First Last"), or empty string if none. */
export function customerPersonalName(customer?: CustomerNameFields | null): string {
  if (!customer) return ''
  return `${customer.first_name || ''} ${customer.last_name || ''}`.trim()
}
