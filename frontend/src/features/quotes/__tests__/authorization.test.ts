import { describe, expect, it } from 'vitest'
import {
  AUTHORIZATION_CONFLICT_MESSAGE,
  authorizationDecisionLabel,
  authorizationTitle,
  canPublishAuthorization,
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
})
