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

const parseAuthorizationEventDetail = (
  detail?: string | null,
): Record<string, unknown> | null => {
  if (!detail) return null
  try {
    const parsed: unknown = JSON.parse(detail)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null
  } catch {
    return null
  }
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
  const parsed = parseAuthorizationEventDetail(detail)
  if (!parsed) {
    // Authorization details are persisted as structured JSON. Never leak a
    // malformed serialized object into the operator-facing history timeline.
    const trimmed = detail.trim()
    return trimmed.startsWith('{') || trimmed.startsWith('[') ? undefined : detail
  }
  const revision = Number(parsed.revision)
  const source = sourceLabel(parsed.source)
  const parts = [
    Number.isFinite(revision) ? `Revision ${revision}` : null,
    parsed.previous_amount != null ? `Previously authorized ${money(parsed.previous_amount)}` : null,
    parsed.delta_amount != null ? `Change ${money(parsed.delta_amount)}` : null,
    parsed.resulting_total != null ? `Resulting total ${money(parsed.resulting_total)}` : null,
    source,
  ].filter((part): part is string => Boolean(part))
  return parts.length ? parts.join(' · ') : undefined
}

const authorizationEventSemanticKey = (event: RepairOrderHistoryEvent): string => {
  const detail = parseAuthorizationEventDetail(event.detail)
  const revision = Number(detail?.revision)
  if (Number.isFinite(revision)) {
    return `${event.event_type}|revision:${revision}`
  }
  if (event.entity_id) {
    return `${event.event_type}|entity:${event.entity_id}`
  }
  return [event.event_type, event.created_at, event.label.trim()].join('|')
}

const authorizationEventPreference = (
  event: RepairOrderHistoryEvent,
  preferredSource: boolean,
): number => (
  (preferredSource ? 4 : 0)
  + (parseAuthorizationEventDetail(event.detail) ? 2 : 0)
  + (event.actor_name ? 1 : 0)
)

/**
 * Merge the same persisted authorization rows exposed by the repair-order
 * detail and authorization-history endpoints. IDs are authoritative when they
 * match; action + revision (or action + quote entity) protects the timeline if
 * two projections ever serialize the same semantic row under different IDs.
 */
export const canonicalizeAuthorizationHistoryEvents = (
  repairOrderEvents: RepairOrderHistoryEvent[],
  authorizationEvents: RepairOrderHistoryEvent[],
): RepairOrderHistoryEvent[] => {
  const bySemanticKey = new Map<string, { event: RepairOrderHistoryEvent; preference: number }>()
  const semanticKeyById = new Map<string, string>()

  const collect = (event: RepairOrderHistoryEvent, preferredSource: boolean) => {
    if (!event.event_type.startsWith('authorization_')) return
    const semanticKey = semanticKeyById.get(event.id) || authorizationEventSemanticKey(event)
    const preference = authorizationEventPreference(event, preferredSource)
    const existing = bySemanticKey.get(semanticKey)
    if (!existing || preference > existing.preference) {
      bySemanticKey.set(semanticKey, { event, preference })
    }
    semanticKeyById.set(event.id, semanticKey)
  }

  authorizationEvents.forEach((event) => collect(event, true))
  repairOrderEvents.forEach((event) => collect(event, false))

  return [...bySemanticKey.values()]
    .map(({ event }) => event)
    .sort((left, right) => (
      new Date(left.created_at).getTime() - new Date(right.created_at).getTime()
      || left.id.localeCompare(right.id)
    ))
}
