import { describe, expect, it } from 'vitest'
import {
  AUTHORIZATION_CONFLICT_MESSAGE,
  authorizationDecisionLabel,
  authorizationTitle,
  canPublishAuthorization,
  canonicalizeAuthorizationHistoryEvents,
  formatAuthorizationEventDetail,
  isAuthorizationConflict,
} from '../authorization'

describe('authorization UI contract', () => {
  it('limits publication to the three staff publisher roles', () => {
    expect(canPublishAuthorization('garage_owner')).toBe(true)
    expect(canPublishAuthorization('garage_admin')).toBe(true)
    expect(canPublishAuthorization('receptionist')).toBe(true)
    expect(canPublishAuthorization('mechanic')).toBe(false)
    expect(canPublishAuthorization('customer')).toBe(false)
    expect(canPublishAuthorization(null)).toBe(false)
  })

  it('distinguishes initial estimates from additional work', () => {
    expect(authorizationTitle({ authorization_type: 'initial_estimate' })).toBe('Estimate authorization')
    expect(authorizationDecisionLabel({ authorization_type: 'initial_estimate' })).toBe('Authorize estimate')
    expect(authorizationTitle({ authorization_type: 'additional_work' })).toBe('Additional work authorization')
    expect(authorizationDecisionLabel({ authorization_type: 'additional_work' })).toBe('Authorize additional work')
  })

  it('recognizes 409 conflicts without treating other failures as stale state', () => {
    expect(isAuthorizationConflict({ response: { status: 409 } })).toBe(true)
    expect(isAuthorizationConflict({ response: { status: 403 } })).toBe(false)
    expect(isAuthorizationConflict(new Error('network'))).toBe(false)
    expect(AUTHORIZATION_CONFLICT_MESSAGE).toMatch(/refreshed.*review.*publishing/i)
  })

  it('formats the immutable event amounts and source for history', () => {
    expect(formatAuthorizationEventDetail(JSON.stringify({
      revision: 2,
      authorization_type: 'additional_work',
      previous_amount: '1000.00',
      delta_amount: '250.50',
      resulting_total: '1250.50',
      source: 'customer_portal',
    }))).toBe(
      'Revision 2 · Previously authorized $1,000.00 · Change $250.50 · Resulting total $1,250.50 · Customer portal',
    )
  })

  it('canonicalizes duplicate endpoint rows by ID and action revision', () => {
    const detail = JSON.stringify({
      revision: 2,
      previous_amount: '1000.00',
      delta_amount: '250.50',
      resulting_total: '1250.50',
      source: 'staff_publication',
    })
    const published = {
      id: 'published-detail', event_type: 'authorization_published', label: 'Additional work published',
      detail, entity_id: 'quote-2', actor_name: null, created_at: '2026-08-11T14:00:00Z',
    }
    const declined = {
      id: 'declined-same-id', event_type: 'authorization_customer_declined', label: 'Additional work declined',
      detail, entity_id: 'quote-2', actor_name: null, created_at: '2026-08-11T14:05:00Z',
    }

    const canonical = canonicalizeAuthorizationHistoryEvents(
      [published, published, declined],
      [
        { ...published, id: 'published-projection', actor_name: 'Olivia Owner' },
        { ...declined, actor_name: 'Casey Customer' },
      ],
    )

    expect(canonical).toHaveLength(2)
    expect(canonical.map((event) => event.event_type)).toEqual([
      'authorization_published',
      'authorization_customer_declined',
    ])
    expect(canonical[0].id).toBe('published-projection')
    expect(canonical[1].actor_name).toBe('Casey Customer')
  })

  it('never returns serialized authorization JSON as visible detail', () => {
    expect(formatAuthorizationEventDetail('{not-valid-json')).toBeUndefined()
    expect(formatAuthorizationEventDetail(JSON.stringify({ unknown: true }))).toBeUndefined()
    expect(formatAuthorizationEventDetail('Customer called the shop')).toBe('Customer called the shop')
  })
})
