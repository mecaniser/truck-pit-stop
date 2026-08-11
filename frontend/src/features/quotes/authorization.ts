import type { Quote, RepairOrderHistoryEvent } from '@/types'

export const AUTHORIZATION_PUBLISHER_ROLES = [
  'garage_owner',
  'garage_admin',
  'receptionist',
] as const

export type AuthorizationHistory = {
  revisions: Quote[]
  events: RepairOrderHistoryEvent[]
}

export const canPublishAuthorization = (role?: string | null): boolean =>
  AUTHORIZATION_PUBLISHER_ROLES.includes(
    role as (typeof AUTHORIZATION_PUBLISHER_ROLES)[number],
  )

export const isAdditionalWorkAuthorization = (
  quote: Pick<Quote, 'authorization_type'>,
): boolean => quote.authorization_type === 'additional_work'

export const authorizationTitle = (
  quote: Pick<Quote, 'authorization_type'>,
): string => isAdditionalWorkAuthorization(quote)
  ? 'Additional work authorization'
  : 'Estimate authorization'

export const authorizationDecisionLabel = (
  quote: Pick<Quote, 'authorization_type'>,
): string => isAdditionalWorkAuthorization(quote)
  ? 'Authorize additional work'
  : 'Authorize estimate'

export const isAuthorizationConflict = (error: unknown): boolean => {
  if (!error || typeof error !== 'object') return false
  const response = (error as { response?: { status?: number } }).response
  return response?.status === 409
}

export const AUTHORIZATION_CONFLICT_MESSAGE =
  'Pricing or authorization status changed. We refreshed the latest repair order; review it before publishing again.'

export const CUSTOMER_AUTHORIZATION_CONFLICT_MESSAGE =
  'This authorization was already decided or replaced. We refreshed the latest status; contact the shop if you need a new revision.'

const money = (value: unknown): string => {
  const parsed = Number(value)
  return Number.isFinite(parsed)
    ? parsed.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
    : '—'
}

const sourceLabel = (source: unknown): string | null => {
  if (typeof source !== 'string' || !source) return null
  const labels: Record<string, string> = {
    staff_publication: 'Staff publication',
    initial_threshold: 'Initial-estimate threshold',
    customer_portal: 'Customer portal',
    magic_link: 'Secure quote link',
  }
  return labels[source] || source.replace(/_/g, ' ')
}

export const formatAuthorizationEventDetail = (
  detail?: string | null,
): string | undefined => {
  if (!detail) return undefined
  try {
    const parsed = JSON.parse(detail) as Record<string, unknown>
    const revision = Number(parsed.revision)
    const previous = money(parsed.previous_amount)
    const delta = money(parsed.delta_amount)
    const resulting = money(parsed.resulting_total)
    const source = sourceLabel(parsed.source)
    return [
      Number.isFinite(revision) ? `Revision ${revision}` : null,
      `Previously authorized ${previous}`,
      `Change ${delta}`,
      `Resulting total ${resulting}`,
      source,
    ].filter(Boolean).join(' · ')
  } catch {
    return detail
  }
}
